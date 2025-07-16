"""
REST API endpoints for AI Cold Calling System
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import json

from database.crud import (
    get_all_leads, create_lead, get_lead, update_lead, delete_lead,
    get_call_records, get_call_statistics, get_lead_statistics,
    bulk_import_leads, get_call_record_by_sid
)
from core.call_manager import call_orchestrator
from scheduler.call_scheduler import call_scheduler
from scheduler.queue_manager import queue_manager
from integrations.twilio_client import TwilioCallManager
from utils.validators import validate_lead_data, validate_twilio_webhook
from utils.helpers import safe_json_loads
from utils.logger import get_logger

logger = get_logger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize components
twilio_manager = TwilioCallManager()

# API Routes

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'services': {
            'database': True,  # Add actual health checks
            'scheduler': call_scheduler.get_status()['running'],
            'twilio': True  # Add Twilio connectivity check
        }
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get system statistics"""
    try:
        days = request.args.get('days', 30, type=int)
        
        call_stats = get_call_statistics(days=days)
        lead_stats = get_lead_statistics()
        queue_stats = queue_manager.get_queue_statistics()
        
        return jsonify({
            'call_stats': call_stats,
            'lead_stats': lead_stats,
            'queue_stats': queue_stats,
            'period_days': days
        })
    except Exception as e:
        logger.error(f"API get stats error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/leads', methods=['GET', 'POST'])
def leads_api():
    """Lead management API"""
    if request.method == 'GET':
        try:
            # Get query parameters
            status = request.args.get('status')
            limit = request.args.get('limit', 100, type=int)
            offset = request.args.get('offset', 0, type=int)
            
            leads = get_all_leads(status=status, limit=limit, offset=offset)
            
            return jsonify({
                'leads': [lead.to_dict() for lead in leads],
                'total': len(leads)
            })
        except Exception as e:
            logger.error(f"API get leads error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'POST':
        try:
            lead_data = request.get_json()
            
            # Validate data
            validation = validate_lead_data(lead_data)
            
            if not validation['valid']:
                return jsonify({
                    'error': 'Validation failed',
                    'errors': validation['errors']
                }), 400
            
            # Create lead
            lead = create_lead(**validation['cleaned_data'])
            
            if lead:
                return jsonify({
                    'success': True,
                    'lead': lead.to_dict()
                }), 201
            else:
                return jsonify({'error': 'Failed to create lead'}), 500
                
        except Exception as e:
            logger.error(f"API create lead error: {e}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/leads/<int:lead_id>', methods=['GET', 'PUT', 'DELETE'])
def lead_detail_api(lead_id):
    """Individual lead management"""
    
    if request.method == 'GET':
        try:
            lead = get_lead(lead_id)
            if not lead:
                return jsonify({'error': 'Lead not found'}), 404
            
            return jsonify({'lead': lead.to_dict()})
        except Exception as e:
            logger.error(f"API get lead error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'PUT':
        try:
            lead = get_lead(lead_id)
            if not lead:
                return jsonify({'error': 'Lead not found'}), 404
            
            update_data = request.get_json()
            
            if update_lead(lead_id, **update_data):
                updated_lead = get_lead(lead_id)
                return jsonify({
                    'success': True,
                    'lead': updated_lead.to_dict()
                })
            else:
                return jsonify({'error': 'Failed to update lead'}), 500
                
        except Exception as e:
            logger.error(f"API update lead error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'DELETE':
        try:
            if delete_lead(lead_id):
                return jsonify({'success': True})
            else:
                return jsonify({'error': 'Failed to delete lead'}), 500
                
        except Exception as e:
            logger.error(f"API delete lead error: {e}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/calls/<int:lead_id>', methods=['POST'])
def start_call_api(lead_id):
    """Start a call to a lead"""
    try:
        success, result = call_orchestrator.start_call(lead_id)
        
        if success:
            return jsonify({
                'success': True,
                'call_sid': result,
                'message': 'Call started successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': result
            }), 500
            
    except Exception as e:
        logger.error(f"API start call error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/calls', methods=['GET'])
def calls_api():
    """Get call records"""
    try:
        lead_id = request.args.get('lead_id', type=int)
        limit = request.args.get('limit', 100, type=int)
        
        calls = get_call_records(lead_id=lead_id, limit=limit)
        
        return jsonify({
            'calls': [call.to_dict() for call in calls],
            'total': len(calls)
        })
    except Exception as e:
        logger.error(f"API get calls error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scheduler/<action>', methods=['POST'])
def scheduler_control_api(action):
    """Control call scheduler"""
    try:
        if action == 'start':
            call_scheduler.start()
            return jsonify({'success': True, 'message': 'Scheduler started'})
        elif action == 'stop':
            call_scheduler.stop()
            return jsonify({'success': True, 'message': 'Scheduler stopped'})
        elif action == 'status':
            status = call_scheduler.get_status()
            return jsonify({'status': status})
        else:
            return jsonify({'error': 'Invalid action'}), 400
            
    except Exception as e:
        logger.error(f"API scheduler control error: {e}")
        return jsonify({'error': str(e)}), 500

# Twilio Webhook Endpoints

@app.route('/webhook/call-start', methods=['POST'])
def twilio_call_start():
    """Handle Twilio call start webhook"""
    try:
        # Validate webhook data
        webhook_data = request.form.to_dict()
        validation = validate_twilio_webhook(webhook_data)
        
        if not validation['valid']:
            logger.error(f"Invalid Twilio webhook data: {validation['errors']}")
            return 'Invalid webhook data', 400
        
        # Get lead ID from query parameters
        lead_id = request.args.get('lead_id', type=int)
        if not lead_id:
            logger.error("Missing lead_id in call start webhook")
            return 'Missing lead ID', 400
        
        # Handle call start
        twiml = call_orchestrator.handle_call_answered(
            validation['call_sid'],
            validation['from_number']
        )
        
        return twiml, 200, {'Content-Type': 'text/xml'}
        
    except Exception as e:
        logger.error(f"Twilio call start webhook error: {e}")
        return 'Internal error', 500

@app.route('/webhook/process-speech/<call_sid>', methods=['POST'])
def twilio_process_speech(call_sid):
    """Handle speech processing webhook"""
    try:
        speech_text = request.form.get('SpeechResult', '').strip()
        confidence = float(request.form.get('Confidence', 1.0))
        
        logger.info(f"Processing speech for call {call_sid}: '{speech_text}' (confidence: {confidence})")
        
        if speech_text:
            # Process conversation turn
            twiml = call_orchestrator.process_conversation_turn(
                call_sid, 
                speech_text, 
                confidence
            )
        else:
            # No speech detected
            twiml = '''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say voice="alice">I didn't catch that. Could you repeat?</Say>
                <Gather input="speech" timeout="3" speechTimeout="2" action="/webhook/process-speech/{}" method="POST">
                </Gather>
                <Say voice="alice">Thank you for your time. Have a great day!</Say>
                <Hangup/>
            </Response>'''.format(call_sid)
        
        return twiml, 200, {'Content-Type': 'text/xml'}
        
    except Exception as e:
        logger.error(f"Speech processing webhook error for {call_sid}: {e}")
        
        # Return error TwiML
        error_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="alice">I'm experiencing technical difficulties. Thank you for your time.</Say>
            <Hangup/>
        </Response>'''
        
        return error_twiml, 200, {'Content-Type': 'text/xml'}

@app.route('/webhook/call-status', methods=['POST'])
def twilio_call_status():
    """Handle Twilio call status updates"""
    try:
        status_data = request.form.to_dict()
        
        call_sid = status_data.get('CallSid', '')
        call_status = status_data.get('CallStatus', '')
        call_duration = status_data.get('CallDuration', 0)
        
        logger.info(f"Call status update: {call_sid} -> {call_status}")
        
        # Handle different call statuses
        if call_status in ['completed', 'failed', 'busy', 'no-answer']:
            call_orchestrator.handle_call_completed(
                call_sid, 
                int(call_duration) if call_duration else 0
            )
        
        return 'OK', 200
        
    except Exception as e:
        logger.error(f"Call status webhook error: {e}")
        return 'Error', 500

@app.route('/webhook/final-response/<call_sid>', methods=['POST'])
def twilio_final_response(call_sid):
    """Handle final response in conversation (e.g. schedule meeting or polite ending)"""
    try:
        speech_text = request.form.get('SpeechResult', '').strip().lower()

        if speech_text:
            if any(word in speech_text for word in ['yes', 'sure', 'interested', 'schedule', 'okay']):
                twiml = call_orchestrator._handle_meeting_request(call_sid, speech_text)
            elif any(word in speech_text for word in ['no', 'not interested', 'decline']):
                twiml = call_orchestrator._handle_rejection(call_sid, speech_text)
            else:
                twiml = call_orchestrator._generate_hangup_twiml("Thanks again for your time. Have a great day!")
        else:
            twiml = call_orchestrator._generate_hangup_twiml("No worries. Thank you and goodbye!")

        return twiml, 200, {'Content-Type': 'text/xml'}

    except Exception as e:
        logger.error(f"Final response webhook error for {call_sid}: {e}")
        error_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="alice">We're sorry, a technical error occurred. Thank you for your time.</Say>
            <Hangup/>
        </Response>'''
        return error_twiml, 200, {'Content-Type': 'text/xml'}

# Error handlers
@app.errorhandler(404)
def api_not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def api_internal_error(error):
    logger.error(f"API internal error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)