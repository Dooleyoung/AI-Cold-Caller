"""
Flask web dashboard for AI Cold Calling System
"""
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
from werkzeug.utils import secure_filename
import csv
import io
import os
from datetime import datetime, timedelta

from database.crud import (
    get_all_leads, create_lead, get_lead, update_lead, delete_lead,
    get_call_records, get_call_statistics, get_lead_statistics,
    bulk_import_leads
)
from core.call_manager import call_orchestrator
from scheduler.call_scheduler import call_scheduler
from scheduler.queue_manager import queue_manager
from utils.validators import validate_lead_data, validate_csv_headers
from utils.helpers import parse_csv_file, export_to_csv, format_duration
from utils.logger import get_logger

logger = get_logger(__name__)

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'

@app.route('/')
def dashboard():
    """Main dashboard showing overview statistics"""
    try:
        # Get statistics
        call_stats = get_call_statistics(days=30)
        lead_stats = get_lead_statistics()
        queue_stats = queue_manager.get_queue_statistics()
        scheduler_status = call_scheduler.get_status()
        
        # Get recent leads and calls
        recent_leads = get_all_leads(limit=10, order_by="created_at")
        recent_calls = get_call_records(limit=10)
        
        return render_template('dashboard.html',
            call_stats=call_stats,
            lead_stats=lead_stats,
            queue_stats=queue_stats,
            scheduler_status=scheduler_status,
            recent_leads=recent_leads,
            recent_calls=recent_calls
        )
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return render_template('error.html', error=str(e))

@app.route('/leads/<int:lead_id>/delete', methods=['POST'])
def delete_lead_route(lead_id):
    """Delete a lead"""
    try:
        success = delete_lead(lead_id)
        if success:
            flash('Lead deleted successfully!', 'success')
        else:
            flash('Failed to delete lead.', 'error')
    except Exception as e:
        logger.error(f"Delete lead error: {e}")
        flash(f'Error deleting lead: {str(e)}', 'error')

    return redirect(url_for('leads_list'))


@app.route('/leads')
def leads_list():
    """List all leads with filtering"""
    try:
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', '')
        search = request.args.get('search', '')
        
        # Get leads with pagination
        limit = 50
        offset = (page - 1) * limit
        
        leads = get_all_leads(status=status if status else None, limit=limit, offset=offset)
        
        # Filter by search term if provided
        if search:
            search_lower = search.lower()
            leads = [lead for lead in leads if 
                    search_lower in lead.name.lower() or 
                    search_lower in (lead.company or '').lower() or
                    search_lower in lead.phone]
        
        return render_template('leads.html',
            leads=leads,
            current_page=page,
            search=search,
            status=status
        )
    except Exception as e:
        logger.error(f"Leads list error: {e}")
        flash(f'Error loading leads: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/leads/new', methods=['GET', 'POST'])
def new_lead():
    """Create new lead"""
    if request.method == 'POST':
        try:
            lead_data = {
                'name': request.form.get('name', ''),
                'phone': request.form.get('phone', ''),
                'email': request.form.get('email', ''),
                'company': request.form.get('company', ''),
                'industry': request.form.get('industry', ''),
                'title': request.form.get('title', ''),
                'priority': request.form.get('priority', 1),
                'notes': request.form.get('notes', '')
            }
            
            # Validate data
            validation = validate_lead_data(lead_data)
            
            if not validation['valid']:
                for field, error in validation['errors'].items():
                    flash(f'{field.title()}: {error}', 'error')
                return render_template('lead_form.html', lead_data=lead_data)
            
            # Create lead
            lead = create_lead(**validation['cleaned_data'])
            
            if lead:
                flash('Lead created successfully!', 'success')
                return redirect(url_for('leads_list'))
            else:
                flash('Failed to create lead', 'error')
                
        except Exception as e:
            logger.error(f"Create lead error: {e}")
            flash(f'Error creating lead: {str(e)}', 'error')
    
    return render_template('lead_form.html')

@app.route('/leads/<int:lead_id>')
def lead_detail(lead_id):
    """Show lead details and call history"""
    try:
        lead = get_lead(lead_id)
        if not lead:
            flash('Lead not found', 'error')
            return redirect(url_for('leads_list'))
        
        # Get call history for this lead
        call_history = get_call_records(lead_id=lead_id)
        
        return render_template('lead_detail.html',
            lead=lead,
            call_history=call_history
        )
    except Exception as e:
        logger.error(f"Lead detail error: {e}")
        flash(f'Error loading lead: {str(e)}', 'error')
        return redirect(url_for('leads_list'))

@app.route('/leads/<int:lead_id>/edit', methods=['GET', 'POST'])
def edit_lead(lead_id):
    """Edit lead information"""
    lead = get_lead(lead_id)
    if not lead:
        flash('Lead not found', 'error')
        return redirect(url_for('leads_list'))
    
    if request.method == 'POST':
        try:
            update_data = {}
            
            # Get form data
            fields = ['name', 'phone', 'email', 'company', 'industry', 'title', 'priority', 'notes']
            for field in fields:
                value = request.form.get(field, '').strip()
                if value:
                    update_data[field] = value
            
            # Update lead
            if update_lead(lead_id, **update_data):
                flash('Lead updated successfully!', 'success')
                return redirect(url_for('lead_detail', lead_id=lead_id))
            else:
                flash('Failed to update lead', 'error')
                
        except Exception as e:
            logger.error(f"Update lead error: {e}")
            flash(f'Error updating lead: {str(e)}', 'error')
    
    return render_template('lead_form.html', lead=lead)

@app.route('/leads/<int:lead_id>/call', methods=['POST'])
def start_call(lead_id):
    """Start a call to a specific lead"""
    try:
        success, result = call_orchestrator.start_call(lead_id)
        
        if success:
            flash(f'Call started successfully! Call SID: {result}', 'success')
        else:
            flash(f'Failed to start call: {result}', 'error')
            
    except Exception as e:
        logger.error(f"Start call error: {e}")
        flash(f'Error starting call: {str(e)}', 'error')
    
    return redirect(url_for('lead_detail', lead_id=lead_id))

@app.route('/leads/upload', methods=['GET', 'POST'])
def upload_leads():
    """Upload leads from CSV file"""
    if request.method == 'POST':
        try:
            if 'file' not in request.files:
                flash('No file selected', 'error')
                return redirect(request.url)
            
            file = request.files['file']
            if file.filename == '':
                flash('No file selected', 'error')
                return redirect(request.url)
            
            if not file.filename.lower().endswith('.csv'):
                flash('Please upload a CSV file', 'error')
                return redirect(request.url)
            
            # Read file content
            file_content = file.read().decode('utf-8')
            
            # Parse CSV
            leads_data = parse_csv_file(file_content)
            
            if not leads_data:
                flash('No valid data found in CSV file', 'error')
                return redirect(request.url)
            
            # Bulk import
            result = bulk_import_leads(leads_data)
            
            flash(f'Import completed: {result["created"]} created, {result["updated"]} updated, {result["errors"]} errors', 'success')
            
            return redirect(url_for('leads_list'))
            
        except Exception as e:
            logger.error(f"Upload leads error: {e}")
            flash(f'Error uploading leads: {str(e)}', 'error')
    
    return render_template('upload_leads.html')

@app.route('/calls')
def calls_list():
    """List all call records"""
    try:
        page = request.args.get('page', 1, type=int)
        limit = 50
        offset = (page - 1) * limit
        
        call_records = get_call_records(limit=limit)
        
        return render_template('calls.html',
            call_records=call_records,
            current_page=page,
            format_duration=format_duration
        )
    except Exception as e:
        logger.error(f"Calls list error: {e}")
        flash(f'Error loading calls: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/queue')
def queue_status():
    """Show call queue status"""
    try:
        queue_stats = queue_manager.get_queue_statistics()
        pending_calls = queue_manager.get_next_calls(limit=100)
        
        return render_template('queue.html',
            queue_stats=queue_stats,
            pending_calls=pending_calls
        )
    except Exception as e:
        logger.error(f"Queue status error: {e}")
        flash(f'Error loading queue: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/scheduler/start', methods=['POST'])
def start_scheduler():
    """Start the call scheduler"""
    try:
        call_scheduler.start()
        flash('Call scheduler started successfully!', 'success')
    except Exception as e:
        logger.error(f"Start scheduler error: {e}")
        flash(f'Error starting scheduler: {str(e)}', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/scheduler/stop', methods=['POST'])
def stop_scheduler():
    """Stop the call scheduler"""
    try:
        call_scheduler.stop()
        flash('Call scheduler stopped successfully!', 'success')
    except Exception as e:
        logger.error(f"Stop scheduler error: {e}")
        flash(f'Error stopping scheduler: {str(e)}', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/reports')
def reports():
    """Show reports and analytics"""
    try:
        # Get statistics for different time periods
        stats_7d = get_call_statistics(days=7)
        stats_30d = get_call_statistics(days=30)
        lead_stats = get_lead_statistics()
        
        return render_template('reports.html',
            stats_7d=stats_7d,
            stats_30d=stats_30d,
            lead_stats=lead_stats
        )
    except Exception as e:
        logger.error(f"Reports error: {e}")
        flash(f'Error loading reports: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/export/leads')
def export_leads():
    """Export leads to CSV"""
    try:
        leads = get_all_leads()
        leads_data = [lead.to_dict() for lead in leads]
        
        csv_content = export_to_csv(leads_data)
        
        output = io.BytesIO()
        output.write(csv_content.encode('utf-8'))
        output.seek(0)
        
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'leads_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    except Exception as e:
        logger.error(f"Export leads error: {e}")
        flash(f'Error exporting leads: {str(e)}', 'error')
        return redirect(url_for('leads_list'))

@app.route('/export/calls')
def export_calls():
    """Export call records to CSV"""
    try:
        calls = get_call_records(limit=10000)
        calls_data = [call.to_dict() for call in calls]
        
        csv_content = export_to_csv(calls_data)
        
        output = io.BytesIO()
        output.write(csv_content.encode('utf-8'))
        output.seek(0)
        
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'calls_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    except Exception as e:
        logger.error(f"Export calls error: {e}")
        flash(f'Error exporting calls: {str(e)}', 'error')
        return redirect(url_for('calls_list'))

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error='Page not found'), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return render_template('error.html', error='Internal server error'), 500

# Template filters
@app.template_filter('datetime')
def datetime_filter(value):
    if value:
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return ''

@app.template_filter('duration')
def duration_filter(value):
    if value:
        return format_duration(value)
    return ''

# ADD THESE WEBHOOK ROUTES TO web/dashboard.py

@app.route('/webhook/call-start', methods=['POST'])
def webhook_call_start():
    """Handle Twilio call start webhook"""
    try:
        lead_id = request.args.get('lead_id', type=int)
        if not lead_id:
            return 'Missing lead ID', 400
        
        # Get call orchestrator
        from core.call_manager import call_orchestrator
        
        # Handle call start
        twiml = call_orchestrator.handle_call_answered(
            request.form.get('CallSid', ''),
            request.form.get('From', '')
        )
        
        return twiml, 200, {'Content-Type': 'text/xml'}
        
    except Exception as e:
        logger.error(f"Webhook call start error: {e}")
        return '''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="alice">Thank you for your time.</Say>
            <Hangup/>
        </Response>''', 200, {'Content-Type': 'text/xml'}

@app.route('/webhook/call-status', methods=['POST'])
def webhook_call_status():
    """Handle Twilio call status updates"""
    try:
        call_sid = request.form.get('CallSid', '')
        call_status = request.form.get('CallStatus', '')
        call_duration = request.form.get('CallDuration', 0)
        
        logger.info(f"Call status update: {call_sid} -> {call_status}")
        
        # Handle call completion
        if call_status in ['completed', 'failed', 'busy', 'no-answer']:
            from core.call_manager import call_orchestrator
            call_orchestrator.handle_call_completed(
                call_sid, 
                int(call_duration) if call_duration else 0
            )
        
        return 'OK', 200
        
    except Exception as e:
        logger.error(f"Webhook call status error: {e}")
        return 'Error', 500

@app.route('/webhook/process-speech/<call_sid>', methods=['POST'])
def webhook_process_speech(call_sid):
    """Handle speech processing webhook"""
    try:
        speech_text = request.form.get('SpeechResult', '').strip()
        confidence = float(request.form.get('Confidence', 1.0))
        
        logger.info(f"Processing speech for {call_sid}: '{speech_text}'")
        
        if speech_text:
            from core.call_manager import call_orchestrator
            twiml = call_orchestrator.process_conversation_turn(
                call_sid, 
                speech_text, 
                confidence
            )
        else:
            twiml = '''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say voice="alice">I didn't catch that. Have a great day!</Say>
                <Hangup/>
            </Response>'''
        
        return twiml, 200, {'Content-Type': 'text/xml'}
        
    except Exception as e:
        logger.error(f"Speech processing error for {call_sid}: {e}")
        return '''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="alice">Thank you for your time.</Say>
            <Hangup/>
        </Response>''', 200, {'Content-Type': 'text/xml'}

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)