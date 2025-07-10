from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from bson.errors import InvalidId
import time # For simulating delays if needed

app = Flask(__name__)
app.secret_key = 'your_strong_secret_key_here' # IMPORTANT: CHANGE THIS TO A REAL, STRONG, RANDOM KEY!

# MongoDB connection
# Ensure your MongoDB connection string is correct and has network access
client = MongoClient('mongodb+srv://kvssmidhun:midhun@cluster0.ckzmfyj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
db = client['travel_booking_db']

# Collections
users_collection = db['users']
flights_collection = db['flights'] # New collection for flights
flight_seats_collection = db['flight_seats'] # New collection for seat availability
trains_collection = db['trains']
bookings_collection = db['bookings']

# --- Constants ---
SEAT_HOLD_TIME_MINUTES = 5 # How long a selected seat is held before being released

# --- Helper Functions ---
def generate_flight_seat_layout(flight_id, travel_date, economy_rows, business_rows, seats_per_row, economy_price, business_price):
    seats = {}
    seat_classes = []

    # Business Class (e.g., rows 1-2)
    for row in range(1, business_rows + 1):
        for char_code in range(ord('A'), ord('A') + seats_per_row):
            seat_num = f"{row}{chr(char_code)}"
            seats[seat_num] = {"status": "available", "user_email": None, "booked_at": None, "class": "business", "price": business_price}
            seat_classes.append("business")

    # Economy Class (e.g., rows 3-12)
    for row in range(business_rows + 1, business_rows + economy_rows + 1):
        for char_code in range(ord('A'), ord('A') + seats_per_row):
            seat_num = f"{row}{chr(char_code)}"
            seats[seat_num] = {"status": "available", "user_email": None, "booked_at": None, "class": "economy", "price": economy_price}
            seat_classes.append("economy")
            
    # Remove duplicates and order for display
    unique_classes = sorted(list(set(seat_classes)), key=lambda x: {"business": 1, "economy": 2}.get(x, 99))

    return {
        "flight_id": ObjectId(flight_id),
        "travel_date": travel_date,
        "seats": seats,
        "layout": {
            "economy_rows": economy_rows,
            "business_rows": business_rows,
            "seats_per_row": seats_per_row
        },
        "seat_classes": unique_classes # To easily display sections in frontend
    }

def release_expired_seats():
    """
    Finds and releases seats that were 'selected' but the hold time has expired.
    This should ideally be run by a separate background task or cron job,
    but for a simple demo, we can call it at the start of relevant routes.
    """
    print("Running background task: Releasing expired seats...")
    current_time = datetime.utcnow()

    # Iterate through all flight_seats documents
    # A more efficient approach for very large databases might involve
    # querying for documents that *might* contain expired selected seats first.
    for flight_seat_doc in flight_seats_collection.find({}):
        doc_id = flight_seat_doc['_id']
        update_fields = {} # Dictionary to hold updates for this specific document

        # Iterate through each seat within the current flight_seat_doc
        for seat_key, seat_info in flight_seat_doc.get('seats', {}).items():
            if seat_info.get('status') == 'selected':
                booked_at = seat_info.get('booked_at')

                # Ensure booked_at is a datetime object for comparison
                # It might be stored as an ISO string from .isoformat()
                if isinstance(booked_at, str):
                    try:
                        booked_at = datetime.fromisoformat(booked_at)
                    except ValueError:
                        print(f"Warning: Could not parse booked_at for seat {seat_key} in doc {doc_id}: {booked_at}")
                        continue # Skip this seat if date format is bad

                if booked_at and (current_time - booked_at).total_seconds() / 60 > SEAT_HOLD_TIME_MINUTES:
                    # If the seat is selected and expired, mark it as available
                    update_fields[f"seats.{seat_key}.status"] = "available"
                    update_fields[f"seats.{seat_key}.user_email"] = None
                    update_fields[f"seats.{seat_key}.booked_at"] = None
                    print(f"Released seat {seat_key} on flight_seat_doc {doc_id}")
        
        # If there are any seats to update in this document, perform the update
        if update_fields:
            flight_seats_collection.update_one(
                {'_id': doc_id},
                {"$set": update_fields}
            )

# --- Sample Data Insertion Functions ---
def insert_sample_train_data():
    if trains_collection.count_documents({}) == 0:
        sample_trains = [
            {"_id": ObjectId(), "name": "Duronto Express", "train_number": "12285", "source": "Hyderabad", "destination": "Delhi", "departure_time": "07:00 AM", "arrival_time": "05:00 AM (next day)", "price": 1800, "date": "2025-07-10"},
            {"_id": ObjectId(), "name": "AP Express", "train_number": "12723", "source": "Hyderabad", "destination": "Vijayawada", "departure_time": "09:00 AM", "arrival_time": "03:00 PM", "price": 450, "date": "2025-07-10"},
            {"_id": ObjectId(), "name": "Gouthami Express", "train_number": "12737", "source": "Guntur", "destination": "Hyderabad", "departure_time": "08:00 PM", "arrival_time": "06:00 AM (next day)", "price": 600, "date": "2025-07-10"},
            {"_id": ObjectId(), "name": "Chennai Express", "train_number": "12839", "source": "Bengaluru", "destination": "Chennai", "departure_time": "10:30 AM", "arrival_time": "05:30 PM", "price": 750, "date": "2025-07-11"},
            {"_id": ObjectId(), "name": "Mumbai Mail", "train_number": "12101", "source": "Hyderabad", "destination": "Mumbai", "departure_time": "06:00 PM", "arrival_time": "09:00 AM (next day)", "price": 1200, "date": "2025-07-10"},
            {"_id": ObjectId(), "name": "Godavari Express", "train_number": "12720", "source": "Vijayawada", "destination": "Hyderabad", "departure_time": "05:00 PM", "arrival_time": "11:00 PM", "price": 400, "date": "2025-07-10"},
        ]
        trains_collection.insert_many(sample_trains)
        print("Sample train data inserted into MongoDB.")

def insert_sample_flight_data():
    if flights_collection.count_documents({}) == 0:
        sample_flights = [
            {"flight_number": "6E 2345", "airline": "IndiGo", "source": "Hyderabad", "destination": "Bengaluru", "departure_time": "14:30", "arrival_time": "16:00", "duration": "1h 30m", "price_economy": 2500, "price_business": 4500, "date": "2025-07-15"},
            {"flight_number": "UK 876", "airline": "Vistara", "source": "Bengaluru", "destination": "Mumbai", "departure_time": "09:00", "arrival_time": "10:45", "duration": "1h 45m", "price_economy": 3200, "price_business": 5800, "date": "2025-07-15"},
            {"flight_number": "AI 501", "airline": "Air India", "source": "Delhi", "destination": "Hyderabad", "departure_time": "18:00", "arrival_time": "20:15", "duration": "2h 15m", "price_economy": 4000, "price_business": 7000, "date": "2025-07-16"},
            {"flight_number": "SG 123", "airline": "SpiceJet", "source": "Hyderabad", "destination": "Chennai", "departure_time": "07:00", "arrival_time": "08:10", "duration": "1h 10m", "price_economy": 2800, "price_business": 5000, "date": "2025-07-15"},
            {"flight_number": "6E 789", "airline": "IndiGo", "source": "Chennai", "destination": "Hyderabad", "departure_time": "10:00", "arrival_time": "11:10", "duration": "1h 10m", "price_economy": 2700, "price_business": 4800, "date": "2025-07-15"},
        ]
        
        for flight in sample_flights:
            # Insert flight and then generate seat layout for it
            flight_id = flights_collection.insert_one(flight).inserted_id
            
            # Define simple layout (you can make this more complex per flight_number if needed)
            economy_rows = 15
            business_rows = 3
            seats_per_row = 6 # A, B, C, D, E, F

            seat_layout_doc = generate_flight_seat_layout(
                flight_id, 
                flight['date'], 
                economy_rows, 
                business_rows, 
                seats_per_row, 
                flight['price_economy'], 
                flight['price_business']
            )
            flight_seats_collection.insert_one(seat_layout_doc)

        print("Sample flight data and initial seat layouts inserted into MongoDB.")

# --- Flask Routes ---

@app.before_request
def before_request():
    # Call the seat release function on every relevant request.
    # In a production app, this would be a dedicated background worker.
    # For a demo, it ensures seats are eventually released if user abandons.
    if request.path.startswith('/flight') or request.path.startswith('/api/flight'):
        release_expired_seats()


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if users_collection.find_one({'email': email}):
            flash('Email already exists!', 'error')
            return render_template('register.html')
        hashed_password = generate_password_hash(password)
        users_collection.insert_one({'email': email, 'password': hashed_password})
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        session.pop('username', None)
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = users_collection.find_one({'email': email})
        if user and check_password_hash(user['password'], password):
            session['email'] = email
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password!', 'error')
            return render_template('login.html')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('email', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    user_email = session['email']
    user_bookings = list(bookings_collection.find({'user_email': user_email}).sort('booking_date', -1))

    for booking in user_bookings:
        if '_id' in booking and isinstance(booking['_id'], ObjectId):
            booking['_id'] = str(booking['_id'])
        
        # Determine vehicle_type for display based on booking_type
        if booking.get('booking_type') == 'bus':
            booking['vehicle_type'] = booking.get('type', 'Bus')
        elif booking.get('booking_type') == 'train':
            booking['vehicle_type'] = f"Train {booking.get('train_number', '')}" if booking.get('train_number') else "Train"
        elif booking.get('booking_type') == 'flight':
            booking['vehicle_type'] = f"Flight {booking.get('flight_number', '')} ({booking.get('airline', '')})"
            # Add seat information for flights
            if booking.get('selected_seats'):
                booking['seats_display'] = ', '.join(booking['selected_seats'])
            else:
                booking['seats_display'] = 'N/A'
        else:
            booking['vehicle_type'] = booking.get('booking_type', 'N/A')

    return render_template('dashboard.html', username=user_email, bookings=user_bookings)

# --- Bus Search and Booking Flow (Client-side search) ---

@app.route('/bus')
def bus():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('bus.html')

@app.route('/confirm_bus_details')
def confirm_bus_details():
    if 'email' not in session:
        return redirect(url_for('login'))

    name = request.args.get('name')
    source = request.args.get('source')
    destination = request.args.get('destination')
    time = request.args.get('time')
    bus_type = request.args.get('type')
    price_per_person = float(request.args.get('price'))
    travel_date = request.args.get('date')
    num_persons = int(request.args.get('persons'))
    bus_id = request.args.get('busId') 

    total_price = price_per_person * num_persons

    booking_details = {
        'name': name,
        'source': source,
        'destination': destination,
        'time': time,
        'type': bus_type, 
        'price_per_person': price_per_person,
        'travel_date': travel_date,
        'num_persons': num_persons,
        'total_price': total_price,
        'item_id': bus_id, 
        'booking_type': 'bus',
        'user_email': session['email']
    }
    session['pending_booking'] = booking_details
    return render_template('confirm_bus_details.html', booking=booking_details)


@app.route('/final_confirm_booking', methods=['POST'])
def final_confirm_booking():
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'User not logged in', 'redirect': url_for('login')}), 401

    booking_data = session.pop('pending_booking', None)

    if not booking_data:
        return jsonify({'success': False, 'message': 'No pending booking to confirm.'}), 400

    try:
        booking_data['booking_date'] = datetime.now().isoformat()
        
        # Check for flight-specific processing (seat updates)
        if booking_data.get('booking_type') == 'flight' and booking_data.get('flight_seat_doc_id') and booking_data.get('selected_seats'):
            flight_seat_doc_id = ObjectId(booking_data['flight_seat_doc_id'])
            selected_seats = booking_data['selected_seats']
            user_email = session['email']

            update_query = {}
            for seat in selected_seats:
                # Atomically update status from 'selected' (by this user) to 'booked'
                update_query[f"seats.{seat}.status"] = "booked"
                # Keep user_email and booked_at as they were during selection
            
            # Use find_one_and_update with a condition to ensure seats are still selected by THIS user
            # This is a critical step for preventing double booking.
            seat_doc_filter = {'_id': flight_seat_doc_id}
            for seat in selected_seats:
                seat_doc_filter[f"seats.{seat}.status"] = "selected"
                seat_doc_filter[f"seats.{seat}.user_email"] = user_email
            
            result = flight_seats_collection.find_one_and_update(
                seat_doc_filter,
                {"$set": update_query},
                return_document=True # Return the updated document
            )
            
            if not result:
                # This means one or more seats were no longer "selected" by this user (e.g., timed out, or another tab).
                flash('Some selected seats were no longer available. Please try re-selecting.', 'error')
                return jsonify({'success': False, 'message': 'Some selected seats were no longer available.', 'redirect': url_for('flight')}), 409 # Conflict

            # Clean up the session data for flight booking specific details not needed in final booking
            booking_data.pop('flight_seat_doc_id', None)
            booking_data.pop('original_flight_id', None)
            # The 'selected_seats' and 'total_price' are fine to keep.

        bookings_collection.insert_one(booking_data)
        flash('Booking confirmed successfully!', 'success')
        return jsonify({
            'success': True,
            'message': 'Booking confirmed successfully!',
            'redirect': url_for('dashboard')
        })
    except Exception as e:
        print(f"Error saving booking to DB: {e}")
        flash(f'Failed to confirm booking: {str(e)}', 'error')
        return jsonify({'success': False, 'message': f'Failed to confirm booking: {str(e)}'}), 500


# --- Train Search and Booking Flow (using client-side const data) ---

@app.route('/train')
def train():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('train.html')

@app.route('/confirm_train_details')
def confirm_train_details():
    if 'email' not in session:
        return redirect(url_for('login'))

    name = request.args.get('name')
    train_number = request.args.get('trainNumber')
    source = request.args.get('source')
    destination = request.args.get('destination')
    departure_time = request.args.get('departureTime')
    arrival_time = request.args.get('arrivalTime')
    price_per_person = float(request.args.get('price'))
    travel_date = request.args.get('date')
    num_persons = int(request.args.get('persons'))
    train_id = request.args.get('trainId') 

    total_price = price_per_person * num_persons

    booking_details = {
        'name': name,
        'train_number': train_number,
        'source': source,
        'destination': destination,
        'departure_time': departure_time,
        'arrival_time': arrival_time,
        'price_per_person': price_per_person,
        'travel_date': travel_date,
        'num_persons': num_persons,
        'total_price': total_price,
        'item_id': train_id, 
        'booking_type': 'train',
        'user_email': session['email']
    }
    session['pending_booking'] = booking_details
    return render_template('confirm_train_details.html', booking=booking_details)


@app.route('/final_confirm_train_booking', methods=['POST'])
def final_confirm_train_booking():
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'User not logged in', 'redirect': url_for('login')}), 401

    booking_data = session.pop('pending_booking', None)

    if not booking_data:
        return jsonify({'success': False, 'message': 'No pending booking to confirm.'}), 400

    try:
        booking_data['booking_date'] = datetime.now().isoformat()
        bookings_collection.insert_one(booking_data)
        flash('Train booking confirmed successfully!', 'success')
        return jsonify({
            'success': True,
            'message': 'Train booking confirmed successfully!',
            'redirect': url_for('dashboard')
        })
    except Exception as e:
        print(f"Error saving train booking to DB: {e}")
        flash(f'Failed to confirm train booking: {str(e)}', 'error')
        return jsonify({'success': False, 'message': f'Failed to confirm train booking: {str(e)}'}), 500

# --- Cancel Booking Route ---
@app.route('/cancel_booking', methods=['POST'])
def cancel_booking():
    if 'email' not in session:
        return redirect(url_for('login')) 

    booking_id = request.form.get('booking_id')
    user_email = session['email']

    if not booking_id:
        flash("Error: Booking ID is missing for cancellation.", 'error')
        return redirect(url_for('dashboard')) 

    try:
        # Convert booking_id to ObjectId as all booking documents have ObjectId _id
        obj_booking_id = ObjectId(booking_id)
        
        # Find the booking to get its details before deleting (especially for flight seats)
        booking_to_cancel = bookings_collection.find_one({'_id': obj_booking_id, 'user_email': user_email})

        if booking_to_cancel:
            # If it's a flight booking, release the seats
            if booking_to_cancel.get('booking_type') == 'flight':
                flight_seat_doc_id = booking_to_cancel.get('flight_seat_doc_id')
                selected_seats = booking_to_cancel.get('selected_seats', [])
                
                if flight_seat_doc_id and selected_seats:
                    update_query = {}
                    for seat in selected_seats:
                        update_query[f"seats.{seat}.status"] = "available"
                        update_query[f"seats.{seat}.user_email"] = None
                        update_query[f"seats.{seat}.booked_at"] = None
                    
                    flight_seats_collection.update_one(
                        {'_id': ObjectId(flight_seat_doc_id)},
                        {"$set": update_query}
                    )
                    print(f"Released seats {selected_seats} for flight_seat_doc {flight_seat_doc_id}")

            result = bookings_collection.delete_one({'_id': obj_booking_id, 'user_email': user_email})
            if result.deleted_count == 1:
                flash(f"Booking cancelled successfully!", 'success')
            else:
                flash(f"Booking not found or not authorized to cancel.", 'error')
        else:
            flash(f"Booking not found or not authorized to cancel.", 'error')
            
    except InvalidId:
        flash(f"Invalid booking ID format.", 'error')
    except Exception as e:
        print(f"Error cancelling booking {booking_id}: {e}")
        flash(f"Failed to cancel booking: {str(e)}", 'error')
    
    return redirect(url_for('dashboard'))

# --- Flight Search and Booking Flow ---

@app.route('/flight', methods=['GET', 'POST'])
def flight():
    if 'email' not in session:
        return redirect(url_for('login'))
    
    query_params = {
        'source': request.args.get('source', ''),
        'destination': request.args.get('destination', ''),
        'date': request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    }
    
    available_flights = []
    if query_params['source'] and query_params['destination'] and query_params['date']:
        flights_query = {
            'source': query_params['source'],
            'destination': query_params['destination'],
            'date': query_params['date']
        }
        available_flights = list(flights_collection.find(flights_query))
        
        # Convert ObjectId for JSON serialization if needed
        for flight in available_flights:
            flight['_id'] = str(flight['_id'])
    
    return render_template('flight.html', flights=available_flights, query=query_params)


@app.route('/select_flight_seats', methods=['GET'])
def select_flight_seats():
    if 'email' not in session:
        return redirect(url_for('login'))

    flight_id = request.args.get('flight_id')
    travel_date = request.args.get('travel_date')
    num_persons = request.args.get('num_persons', type=int)

    if not flight_id or not travel_date or not num_persons:
        flash("Missing flight details to select seats.", 'error')
        return redirect(url_for('flight'))
    
    # Store these in session for later confirmation if needed
    session['current_flight_selection'] = {
        'flight_id': flight_id,
        'travel_date': travel_date,
        'num_persons': num_persons
    }

    flight_obj = flights_collection.find_one({'_id': ObjectId(flight_id)})
    if not flight_obj:
        flash("Flight not found.", 'error')
        return redirect(url_for('flight'))
    
    # Fetch existing seat layout for this flight and date
    flight_seat_doc = flight_seats_collection.find_one({
        "flight_id": ObjectId(flight_id),
        "travel_date": travel_date
    })

    if not flight_seat_doc:
        # This shouldn't happen if data insertion works correctly, but as a fallback
        flash("Seat layout not found for this flight.", 'error')
        return redirect(url_for('flight'))
    
    # Convert ObjectId for the document itself for passing to frontend
    flight_seat_doc['_id'] = str(flight_seat_doc['_id'])
    flight_obj['_id'] = str(flight_obj['_id'])

    return render_template('select_flight_seats.html', 
                            flight=flight_obj, 
                            flight_seat_doc=flight_seat_doc,
                            num_persons=num_persons)

# --- API Endpoints for Real-time Seat Selection ---

@app.route('/api/flight/seat_status/<flight_seat_doc_id>', methods=['GET'])
def get_seat_status(flight_seat_doc_id):
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        seat_doc = flight_seats_collection.find_one({'_id': ObjectId(flight_seat_doc_id)})
        if not seat_doc:
            return jsonify({'error': 'Seat map not found'}), 404
        
        # Only send relevant seat status data
        simplified_seats = {
            seat_id: {
                "status": data["status"],
                "class": data["class"],
                "price": data["price"]
            }
            for seat_id, data in seat_doc.get('seats', {}).items()
        }
        
        return jsonify(simplified_seats), 200
    except InvalidId:
        return jsonify({'error': 'Invalid Flight Seat Document ID'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/flight/select_seat', methods=['POST'])
def select_seat():
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    user_email = session['email']
    data = request.json
    flight_seat_doc_id = data.get('flight_seat_doc_id')
    seat_id = data.get('seat_id')

    if not flight_seat_doc_id or not seat_id:
        return jsonify({'success': False, 'message': 'Missing flight seat document ID or seat ID'}), 400

    try:
        obj_flight_seat_doc_id = ObjectId(flight_seat_doc_id)
        current_time = datetime.utcnow()
        
        # Atomically try to select the seat:
        # 1. Seat must be 'available'
        # 2. Or, if it's 'selected', it must be selected by *this* user (for re-selection/double click)
        result = flight_seats_collection.find_one_and_update(
            {
                '_id': obj_flight_seat_doc_id,
                "$or": [
                    { f"seats.{seat_id}.status": "available" },
                    { f"seats.{seat_id}.status": "selected", f"seats.{seat_id}.user_email": user_email }
                ]
            },
            {
                "$set": {
                    f"seats.{seat_id}.status": "selected",
                    f"seats.{seat_id}.user_email": user_email,
                    f"seats.{seat_id}.booked_at": current_time.isoformat() # Store as ISO string
                }
            },
            return_document=True # Return the modified document
        )

        if result:
            seat_info = result['seats'].get(seat_id)
            if seat_info and seat_info['user_email'] == user_email: # Double check after update
                return jsonify({'success': True, 'status': 'selected', 'seat_info': seat_info}), 200
            else:
                return jsonify({'success': False, 'message': 'Seat already taken or not available.'}), 409 # Conflict
        else:
            return jsonify({'success': False, 'message': 'Seat not available or invalid request.'}), 409 # Conflict

    except InvalidId:
        return jsonify({'success': False, 'message': 'Invalid Flight Seat Document ID'}), 400
    except Exception as e:
        print(f"Error selecting seat: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/flight/release_seat', methods=['POST'])
def release_seat():
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    user_email = session['email']
    data = request.json
    flight_seat_doc_id = data.get('flight_seat_doc_id')
    seat_id = data.get('seat_id')

    if not flight_seat_doc_id or not seat_id:
        return jsonify({'success': False, 'message': 'Missing flight seat document ID or seat ID'}), 400

    try:
        obj_flight_seat_doc_id = ObjectId(flight_seat_doc_id)
        
        # Atomically try to release the seat: only if it's 'selected' by *this* user
        result = flight_seats_collection.find_one_and_update(
            {
                '_id': obj_flight_seat_doc_id,
                f"seats.{seat_id}.status": "selected",
                f"seats.{seat_id}.user_email": user_email
            },
            {
                "$set": {
                    f"seats.{seat_id}.status": "available",
                    f"seats.{seat_id}.user_email": None,
                    f"seats.{seat_id}.booked_at": None
                }
            },
            return_document=True
        )

        if result:
            return jsonify({'success': True, 'status': 'available'}), 200
        else:
            return jsonify({'success': False, 'message': 'Seat not held by you or not found.'}), 409 # Conflict

    except InvalidId:
        return jsonify({'success': False, 'message': 'Invalid Flight Seat Document ID'}), 400
    except Exception as e:
        print(f"Error releasing seat: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/confirm_flight_booking', methods=['POST'])
def confirm_flight_booking():
    if 'email' not in session:
        flash("You need to be logged in to confirm booking.", 'error')
        return jsonify({'success': False, 'message': 'You need to be logged in to confirm booking.'}), 401

    user_email = session['email']
    data = request.json
    
    flight_id = data.get('flight_id')
    flight_seat_doc_id = data.get('flight_seat_doc_id')
    selected_seats = data.get('selected_seats')
    total_price = data.get('total_price')
    travel_date = data.get('travel_date') # Passed from JavaScript now

    if not flight_id or not flight_seat_doc_id or not selected_seats or not total_price or not travel_date:
        flash("Missing flight booking details.", 'error')
        return jsonify({'success': False, 'message': 'Missing flight booking details.'}), 400

    try:
        flight_obj = flights_collection.find_one({'_id': ObjectId(flight_id)})
        if not flight_obj:
            flash("Flight not found.", 'error')
            return jsonify({'success': False, 'message': 'Flight not found.'}), 404

        booking_details = {
            'booking_type': 'flight',
            'flight_id': ObjectId(flight_id), # Reference to the flight details
            'flight_seat_doc_id': ObjectId(flight_seat_doc_id), # Reference to the specific seat layout document
            'flight_number': flight_obj.get('flight_number'),
            'airline': flight_obj.get('airline'),
            'source': flight_obj.get('source'),
            'destination': flight_obj.get('destination'),
            'departure_time': flight_obj.get('departure_time'),
            'arrival_time': flight_obj.get('arrival_time'),
            'travel_date': travel_date,
            'selected_seats': selected_seats,
            'num_persons': len(selected_seats), # Number of persons is number of seats
            'total_price': total_price,
            'user_email': user_email,
            'booking_date': datetime.now().isoformat(),
        }

        # Store these in session, then redirect to a final confirmation page (optional)
        # For simplicity, we'll directly call final_confirm_booking using AJAX.
        session['pending_booking'] = booking_details
        
        # Redirect to the main final confirmation route, which will handle the actual DB insertion
        return jsonify({'success': True, 'redirect_to_final_confirm': url_for('final_confirm_booking')})

    except InvalidId:
        flash("Invalid Flight ID or Seat Document ID.", 'error')
        return jsonify({'success': False, 'message': 'Invalid ID.'}), 400
    except Exception as e:
        print(f"Error preparing flight booking: {e}")
        flash(f"Failed to prepare flight booking: {str(e)}", 'error')
        return jsonify({'success': False, 'message': f"Failed to prepare flight booking: {str(e)}"}), 500


if __name__ == '__main__':
    # Initial data population
    insert_sample_train_data() 
    insert_sample_flight_data() # Insert flight data and populate seat layouts
    app.run(debug=True)