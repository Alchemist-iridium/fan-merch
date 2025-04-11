from flask import request, Blueprint,current_app, render_template, redirect, url_for, session, flash, current_app, send_file, jsonify
from datetime import datetime, timezone,timedelta
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy import cast, String, and_
from app.models import *
# this line needs modification
from app.extensions import db
import uuid
from sqlalchemy.sql import func

import json

from collections import defaultdict
import pandas as pd
import shutil

import html
import re

import csv
from io import StringIO

from dateutil.relativedelta import relativedelta

from flask_login import login_user, logout_user, login_required, current_user

from app.admin_utils import *
# login page for the admins, which is different from the user login page (for customers and artists)

# Configure basic logging to output to console (you can adjust this later)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)



admin_interface = Blueprint('admin_interface', __name__)

VALID_ADMIN_ROLES = {
    'artwork_approval_admin',
    'product_approval_admin',
    'production_round_admin',
    'warehouse_admin',
    'delivery_admin',
    'info_admin',
    'finance_admin',
    'customer_service_admin'
}



@admin_interface.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    # If admin is already logged in, redirect to appropriate dashboard
    if current_user.is_authenticated:
        if current_user.role in VALID_ADMIN_ROLES:  # Assuming VALID_ADMIN_ROLES from admin_utils.py
            if current_user.role == 'artwork_approval_admin':
                return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))
            elif current_user.role == 'production_round_admin':
                return redirect(url_for('admin_interface.production_round_admin_dashboard', category='active'))
            elif current_user.role == 'product_approval_admin':
                return redirect(url_for('admin_interface.product_approval_admin_dashboard'))
            elif current_user.role == 'warehouse_admin':
                return redirect(url_for('admin_interface.warehouse_admin_dashboard'))
            elif current_user.role == 'delivery_admin':
                return redirect(url_for('admin_interface.delivery_admin_dashboard'))
            elif current_user.role == 'info_admin':
                return redirect(url_for('admin_interface.info_admin_dashboard'))
            elif current_user.role == 'finance_admin':
                return redirect(url_for('admin_interface.finance_admin_dashboard'))
            else:
                flash("Unknown admin role. Please contact support.")
                return redirect(url_for('admin_interface.admin_login'))
        else:
            flash("Please use the appropriate login page for your role.")
            return redirect(url_for('user_interface.login'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Check if the email belongs to any admin role
        admin = Admin.query.filter_by(email=email).first()

        if admin and check_password_hash(admin.password_hash, password):
            login_user(admin)  # Log in the admin with Flask-Login
            flash("Admin login successful!")

            # Redirect to the appropriate admin dashboard based on role
            if admin.role == 'artwork_approval_admin':
                return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))
            elif admin.role == 'production_round_admin':
                return redirect(url_for('admin_interface.production_round_admin_dashboard', category='active'))
            elif admin.role == 'product_approval_admin':
                return redirect(url_for('admin_interface.product_approval_admin_dashboard'))
            elif admin.role == 'warehouse_admin':
                return redirect(url_for('admin_interface.warehouse_admin_dashboard'))
            elif admin.role == 'delivery_admin':
                return redirect(url_for('admin_interface.delivery_admin_dashboard'))
            elif admin.role == 'info_admin':
                return redirect(url_for('admin_interface.info_admin_dashboard'))
            elif admin.role == 'finance_admin':
                return redirect(url_for('admin_interface.finance_admin_dashboard'))
            else:
                flash("Unknown admin role detected.")
                return redirect(url_for('admin_interface.admin_login'))
        else:
            error = "Wrong email or password"
            return render_template('admin/account/admin_login.html', error=error)

    return render_template('admin/account/admin_login.html')




@admin_interface.route('/logout')
@login_required  # Optional, ensures only logged-in users can logout
def logout():
    logout_user()  # Clear the Flask-Login session
    flash("You have been logged out.")
    return redirect(url_for('admin_interface.admin_login'))


# Artwork Approval Admin Dashboard
# search the artwork to be picked
# approve/disapprove artwork
# approve/disapprove artwork update


@admin_interface.route('/artwork_approval_admin_dashboard', methods=['GET', 'POST'])
@admin_required('artwork_approval_admin')
def artwork_approval_admin_dashboard(admin_id):

    search_query = request.args.get('search_query', '').strip()

    # Pending Artworks (not picked and pending approval)
    pending_artworks = Artwork.query.filter_by(approval_status='Pending', picked_by_admin_id=None).all()

    # Pending Updates (not picked and pending review)
    pending_updates = ArtworkUpdate.query.filter(
        ArtworkUpdate.status == 'Pending',
        ArtworkUpdate.picked_by_admin_id == None
    ).all()

    # Search functionality (applies to both artworks and updates)
    search_artworks = []
    search_updates = []
    if search_query:
        search_artworks = Artwork.query.filter(
            Artwork.approval_status == 'Pending',
            Artwork.picked_by_admin_id == None,
            Artwork.hard_tags.ilike(f"%{search_query}%")
        ).all()
        search_updates = ArtworkUpdate.query.filter(
            ArtworkUpdate.status == 'Pending',
            ArtworkUpdate.approval_admin_id == None,
            ArtworkUpdate.proposed_hard_tags.ilike(f"%{search_query}%")
        ).all()

    return render_template(
        'admin/artwork_approval_admin/artwork_approval_admin_dashboard.html',
        pending_artworks=pending_artworks,
        pending_updates=pending_updates,
        search_artworks=search_artworks,
        search_updates=search_updates,
        search_query=search_query
    )





# artwork_approval_admin can search artworks by hardtag (ip name) to get selected
# also can pick all the search result to workspace

@admin_interface.route('/search_artworks', methods=['GET', 'POST'])
@admin_required('artwork_approval_admin')
def search_artworks(admin_id):

    search_query = request.args.get('search_query', '').strip()

    if not search_query:
        flash("Please enter a search query.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    # Fetch search results
    search_results = Artwork.query.filter(
        Artwork.approval_status == 'Pending',
        Artwork.picked_by_admin_id == None,
        Artwork.hard_tags.ilike(f"%{search_query}%")
    ).all()

    if request.method == 'POST':
        # Handle "Pick All Artwork"
        for artwork in search_results:
            if not artwork.picked_by_admin_id:
                artwork.picked_by_admin_id = uuid.UUID(session['user_id'])
        db.session.commit()
        flash("All artworks in the search results have been picked.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    return render_template(
        'admin/artwork_approval_admin/artwork_search_results.html',
        search_results=search_results,
        search_query=search_query
    )



# admin picks the artwork from dashboard to personal workspace to approve or disapprove.
# The picked artwork is not going to be displayed on the dashboard.

@admin_interface.route('/artwork_approval_workspace', methods=['GET'])
@admin_required('artwork_approval_admin')
def artwork_approval_workspace(admin_id):
    # Fetch pending artworks for the admin
    artworks = Artwork.query.filter_by(picked_by_admin_id=admin_id, approval_status='Pending').all()

    # Group artworks by pending normalized tags
    tag_to_artworks = defaultdict(list)
    artworks_to_update = []  # Collect artworks needing tag_approvals initialization

    for artwork in artworks:
        # Initialize tag_approvals if empty, using normalized tags
        if not artwork.tag_approvals:
            original_tags = [tag.strip() for tag in artwork.hard_tags.split('#') if tag.strip()]
            normalized_tags = [Artwork.normalize_tag(tag) for tag in original_tags]
            artwork.tag_approvals = {tag: "Pending" for tag in normalized_tags}
            artworks_to_update.append(artwork)
        
        # Group by pending tags directly from tag_approvals
        for normalized_tag, status in artwork.tag_approvals.items():
            if status == "Pending":
                tag_to_artworks[normalized_tag].append(artwork)

    # Commit all updates in one transaction
    if artworks_to_update:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Error initializing tag approvals: {str(e)}", "error")
            return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    return render_template('admin/artwork_approval_admin/artwork_approval_workspace.html', tag_to_artworks=dict(tag_to_artworks))






@admin_interface.route('/export_artworks/<tag>', methods=['POST'])
@admin_required('artwork_approval_admin')
def export_artworks(admin_id, tag):
    artworks = Artwork.query.filter(
        func.lower(Artwork.hard_tags).like(f'%{tag.lower()}%'),
        Artwork.picked_by_admin_id == admin_id,
        Artwork.approval_status == 'Pending'
    ).all()
    
    sanitized_tag = Artwork.sanitize_filename(tag)
    base_temp_dir = f'/tmp/export_{sanitized_tag}'
    os.makedirs(base_temp_dir, exist_ok=True)
    tag_dir = os.path.join(base_temp_dir, sanitized_tag)
    os.makedirs(tag_dir, exist_ok=True)

    folder_counts = defaultdict(int)
    for artwork in artworks:
        base_folder_name = Artwork.sanitize_filename(artwork.title)
        folder_counts[base_folder_name] += 1
        folder_name = (f"{base_folder_name}-{folder_counts[base_folder_name] - 1}"
                      if folder_counts[base_folder_name] > 1 else base_folder_name)
        artwork_dir = os.path.join(tag_dir, folder_name)
        os.makedirs(artwork_dir, exist_ok=True)
        
        image_src = os.path.join(current_app.root_path, 'static', artwork.image_path)
        image_dst = os.path.join(artwork_dir, os.path.basename(artwork.image_path))
        if os.path.exists(image_src):
            shutil.copyfile(image_src, image_dst)
        else:
            print(f"Warning: Image not found at {image_src}")
        
        text_file_path = os.path.join(artwork_dir, 'info.txt')
        with open(text_file_path, 'w', encoding='utf-8') as f:
            f.write(f'ID: {artwork.id}\n')
            f.write(f'Title: {artwork.title}\n')
            f.write(f'Description: {artwork.description if artwork.description else "N/A"}\n')
            f.write(f'Manufacturing Specs: {artwork.manufacturing_specs if artwork.manufacturing_specs else "N/A"}\n')
    
    # Create the checklist CSV file with correct name
    checklist_path = os.path.join(tag_dir, f'checklist.csv')
    with open(checklist_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(['Artwork ID', 'Title', 'Approve/Disapprove', 'Detail'])
        for artwork in artworks:
            writer.writerow([str(artwork.id), artwork.title, '', ''])  # Ensure ID is a string

    zip_path = f'/tmp/artworks_{sanitized_tag}.zip'
    shutil.make_archive(zip_path.replace('.zip', ''), 'zip', base_temp_dir)
    response = send_file(
        zip_path,
        as_attachment=True,
        download_name=f'artworks_{sanitized_tag}.zip'
    )
    
    # Cleanup to prevent duplicate files
    shutil.rmtree(base_temp_dir, ignore_errors=True)
    os.remove(zip_path)
    
    return response


# pick to workspace

@admin_interface.route('/pick_artwork/<uuid6:artwork_id>', methods=['POST'])
@admin_required('artwork_approval_admin')
def pick_artwork(admin_id, artwork_id):

    artwork = Artwork.query.get_or_404(artwork_id)

    if artwork.picked_by_admin_id:
        flash("This artwork has already been picked by another admin.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    # Assign the artwork to the current admin
    artwork.picked_by_admin_id = admin_id
    db.session.commit()

    flash(f"Artwork '{artwork.title}' has been added to your workspace.")
    return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))


@admin_interface.route('/unpick_artwork/<uuid6:artwork_id>', methods=['POST'])
@admin_required('artwork_approval_admin')
def unpick_artwork(admin_id, artwork_id):

    artwork = Artwork.query.get_or_404(artwork_id)

    if artwork.picked_by_admin_id != admin_id:
        flash("You can only unpick artworks from your own workspace.")
        return redirect(url_for('admin_interface.artwork_approval_workspace'))

    # Unassign the artwork
    artwork.picked_by_admin_id = None
    db.session.commit()

    flash(f"Artwork '{artwork.title}' has been removed from your workspace.")
    return redirect(url_for('admin_interface.artwork_approval_workspace'))



@admin_interface.route('/approve_artwork/<uuid6:artwork_id>/<tag>', methods=['POST'])
@admin_required('artwork_approval_admin')
def approve_artwork(admin_id, artwork_id, tag):
    logger.debug(f"Starting approval: artwork_id={artwork_id}, tag={tag}, admin_id={admin_id}")
    
    artwork = Artwork.query.get_or_404(artwork_id)
    logger.debug(f"Artwork loaded: id={artwork.id}, hard_tags={artwork.hard_tags}, "
                 f"tag_approvals={artwork.tag_approvals}, approval_status={artwork.approval_status}")
    
    # Normalize the incoming tag
    normalized_tag = Artwork.normalize_tag(tag)
    
    # Validate tag against hard_tags (normalize both for comparison)
    hard_tags_clean = artwork.hard_tags.strip()
    tags = [Artwork.normalize_tag(t) for t in hard_tags_clean.split('#') if t.strip()]
    if normalized_tag not in tags:
        flash(f"Tag '{tag}' is not associated with this artwork.", "error")
        logger.debug(f"Tag '{normalized_tag}' not in hard_tags: {tags}")
        return redirect(url_for('admin_interface.artwork_approval_workspace'))
    
    # Approve the normalized tag in tag_approvals
    if normalized_tag in artwork.tag_approvals and artwork.tag_approvals[normalized_tag] == "Pending":
        artwork.tag_approvals = dict(artwork.tag_approvals)  # Force change detection
        artwork.tag_approvals[normalized_tag] = "Approved"
        artwork.approval_admin_id = admin_id
        logger.debug(f"Updated: tag_approvals={artwork.tag_approvals}, approval_admin_id={artwork.approval_admin_id}")
        
        all_approved = all(status == "Approved" for status in artwork.tag_approvals.values())
        logger.debug(f"All tags approved? {all_approved}")
        
        if all_approved:
            artwork.approval_status = "Approved"
            update_artwork_timestamp(artwork, commit=False)
        
        try:
            db.session.commit()
            logger.debug(f"Committed: approval_status={artwork.approval_status}, tag_approvals={artwork.tag_approvals}")
            if all_approved:
                artist_id = artwork.artist_id
                message = f"Your artwork '{artwork.title}' has been approved."
                flash(f"Artwork '{artwork.title}' is fully approved!", "success")
                Notification.send_notification(user_id=artist_id, message=message, type='artwork')
            else:
                flash(f"Tag '{tag}' for artwork '{artwork.title}' has been approved.", "success")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Commit failed: {str(e)}")
            flash("An error occurred while approving the tag.", "error")
    else:
        flash(f"Tag '{tag}' cannot be approved.", "warning")
        logger.debug(f"Tag '{normalized_tag}' not eligible: tag_approvals={artwork.tag_approvals}")

    return redirect(url_for('admin_interface.artwork_approval_workspace'))



@admin_interface.route('/disapprove_artwork/<uuid6:artwork_id>', methods=['GET', 'POST'])
@admin_required('artwork_approval_admin')
def disapprove_artwork(admin_id, artwork_id):
    # Retrieve the artwork
    artwork = Artwork.query.get_or_404(artwork_id)

    # Handle POST request
    if request.method == 'POST':
        # Retrieve the disapproval reason from the form
        reason = request.form.get('disapprove_reason', None)
        if reason:
            # Clean the reason by removing HTML tags
            clean_reason = re.sub(r'<[^>]+>', '', html.unescape(reason))
            
            # Update artwork status to disapproved, add the cleaned reason, and record the admin's ID
            artwork.approval_status = 'Disapproved'
            artwork.disapproval_reason = clean_reason  # Store cleaned reason
            artwork.approval_admin_id = admin_id

            update_artwork_timestamp(artwork, commit=False)
            db.session.commit()

            # Send notification to the artist about disapproval using cleaned reason
            artist_id = artwork.artist_id
            message = f"Your artwork '{artwork.title}' has been disapproved. Reason: {clean_reason}"
            Notification.send_notification(user_id=artist_id, message=message, type='artwork')

            flash(f"Artwork '{artwork.title}' has been disapproved.")
            return redirect(url_for('admin_interface.artwork_approval_workspace'))
        else:
            flash("Please provide a reason for disapproval.")
            return render_template('admin/artwork_approval_admin/disapprove_artwork.html', artwork=artwork)

    # GET request - render the form
    return render_template('admin/artwork_approval_admin/disapprove_artwork.html', artwork=artwork)

# batch process of approve/disapprove, currently only support csv file.
# the format is the same as that of the exported checklist.csv


@admin_interface.route('/batch_artwork_approve_disapprove/<tag>', methods=['GET', 'POST'])
@admin_required('artwork_approval_admin')
def batch_artwork_approve_disapprove(admin_id, tag):
    normalized_tag = Artwork.normalize_tag(tag)

    if request.method == 'POST':
        if 'csv_file' in request.files and request.files['csv_file']:
            file = request.files['csv_file']
            if not file.filename or not allowed_file(file.filename):
                flash("Invalid or no file selected. Only .csv and .xlsx allowed.", "error")
                return redirect(url_for('admin_interface.artwork_approval_workspace'))

            # Read CSV or XLSX
            if file.filename.endswith('.csv'):
                stream = StringIO(file.stream.read().decode("UTF-8"), newline=None)
                reader = csv.DictReader(stream)
            elif file.filename.endswith('.xlsx'):
                import pandas as pd
                df = pd.read_excel(file.stream)
                reader = df.to_dict(orient='records')
            else:
                flash("Unsupported file format.", "error")
                return redirect(url_for('admin_interface.artwork_approval_workspace'))

            required_columns = ['Artwork ID', 'Title', 'Approve/Disapprove', 'Detail']
            if not all(col in reader.fieldnames for col in required_columns):
                flash("File must contain: Artwork ID, Title, Approve/Disapprove, Detail", "error")
                return redirect(url_for('admin_interface.artwork_approval_workspace'))

            rows = list(reader)
            logger.debug(f"File rows parsed: {rows}")
            session['batch_rows'] = rows
            session['batch_tag'] = tag
            return render_template('admin/artwork_approval_admin/preview_batch.html', tag=tag, rows=rows)

        elif 'confirm' in request.form and 'batch_rows' in session and 'batch_tag' in session:
            rows = session.pop('batch_rows')
            tag = session.pop('batch_tag')
            normalized_tag = Artwork.normalize_tag(tag)
            successes = []
            errors = []

            for row in rows:
                artwork_id_str = row['Artwork ID'].strip()
                title = row['Title'].strip()
                action = row['Approve/Disapprove'].strip().lower()
                detail = row['Detail'].strip()

                logger.debug(f"Processing row: ID={artwork_id_str}, Title={title}, Action={action}, Detail={detail}")

                # Convert string to UUID object
                try:
                    artwork_id = to_uuid(artwork_id_str, "Artwork ID")  # Returns uuid.UUID object
                except ValueError as e:
                    errors.append(str(e))
                    continue

                # Query artwork with UUID object
                artwork = Artwork.query.get(artwork_id)
                if not artwork:
                    errors.append(f"Artwork not found: {artwork_id_str}")
                    continue
                if artwork.title != title:
                    errors.append(f"Title mismatch for ID {artwork_id_str}: expected '{artwork.title}', got '{title}'")
                    continue

                # Validate tag
                tags = [Artwork.normalize_tag(t) for t in artwork.hard_tags.split('#') if t.strip()]
                if normalized_tag not in tags:
                    errors.append(f"Tag '{tag}' not in artwork '{title}'")
                    continue

                # Process action
                if action == "approve":
                    if normalized_tag in artwork.tag_approvals and artwork.tag_approvals[normalized_tag] == "Pending":
                        artwork.tag_approvals = dict(artwork.tag_approvals)
                        artwork.tag_approvals[normalized_tag] = "Approved"
                        artwork.approval_admin_id = admin_id
                        all_approved = all(status == "Approved" for status in artwork.tag_approvals.values())
                        if all_approved:
                            artwork.approval_status = "Approved"

                            update_artwork_timestamp(artwork, commit=False)

                            Notification.send_notification(
                                user_id=artwork.artist_id,
                                message=f"Your artwork '{artwork.title}' has been approved.",
                                type='artwork'
                            )
                            successes.append(f"Approved artwork '{title}' fully")
                        else:
                            successes.append(f"Approved tag '{tag}' for '{title}'")
                elif action == "disapprove":
                    if not detail:
                        errors.append(f"Disapproval reason required for '{title}'")
                        continue
                    artwork.approval_status = "Disapproved"
                    
                    update_artwork_timestamp(artwork, commit=False)

                    artwork.disapproval_reason = detail
                    artwork.approval_admin_id = admin_id
                    Notification.send_notification(
                        user_id=artwork.artist_id,
                        message=f"Your artwork '{artwork.title}' has been disapproved. Reason: {detail}",
                        type='artwork'
                    )
                    successes.append(f"Disapproved '{title}' with reason: {detail}")
                else:
                    errors.append(f"Invalid action '{action}' for '{title}'")

            # Commit changes
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                errors.append(f"Database commit failed: {str(e)}")
                successes = []

            return render_template('admin/artwork_approval_admin/batch_storage_result.html', 
                                 tag=tag, successes=successes, errors=errors)

        else:
            flash("No valid action or file provided.", "error")
            return redirect(url_for('admin_interface.artwork_approval_workspace'))

    return render_template('admin/artwork_approval_admin/upload_batch.html', tag=tag)



# artwork update


@admin_interface.route('/search_artwork_updates', methods=['GET', 'POST'])
@admin_required('artwork_approval_admin')
def search_artwork_updates(admin_id):

    search_query = request.args.get('search_query', '').strip()

    if not search_query:
        flash("Please enter a search query.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    # Fetch search results for artwork updates
    search_results = ArtworkUpdate.query.filter(
        ArtworkUpdate.status == 'Pending',
        ArtworkUpdate.picked_by_admin_id == None,
        ArtworkUpdate.proposed_hard_tags.ilike(f"%{search_query}%")
    ).all()

    if request.method == 'POST':
        # Handle "Pick All Updates"
        for update in search_results:
            if not update.picked_by_admin_id:
                update.picked_by_admin_id = admin_id
        db.session.commit()
        flash("All artwork updates in the search results have been picked.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    return render_template(
        'admin/artwork_approval_admin/artwork_update_search_result.html',
        search_results=search_results,
        search_query=search_query
    )




@admin_interface.route('/artwork_update_workspace', methods=['GET'])
@admin_required('artwork_approval_admin')
def artwork_update_workspace(admin_id):
    updates = ArtworkUpdate.query.filter_by(picked_by_admin_id=admin_id, status='Pending').all()
    
    tag_to_updates = defaultdict(list)
    for update in updates:
        if update.tag_approvals:
            # Group by tags that are still "Pending"
            any_pending = False
            for tag, status in update.tag_approvals.items():
                if status == "Pending":
                    tag_to_updates[tag].append(update)
                    any_pending = True
            if not any_pending:
                tag_to_updates['All Tags Approved'].append(update)
        else:
            tag_to_updates['No Tags'].append(update)
    
    return render_template(
        'admin/artwork_approval_admin/artwork_update_workspace.html',
        tag_to_updates=dict(tag_to_updates)
    )





@admin_interface.route('/export_artwork_updates/<tag>', methods=['POST'])
@admin_required('artwork_approval_admin')
def export_artwork_updates(admin_id, tag):
    # Fetch updates with the specified proposed_hard_tags, picked by the admin, and pending
    updates = ArtworkUpdate.query.filter(
        ArtworkUpdate.proposed_hard_tags.like(f'%{tag}%'),
        ArtworkUpdate.picked_by_admin_id == admin_id,
        ArtworkUpdate.status == 'Pending'
    ).all()
    
    # Create a temporary base directory
    base_temp_dir = f'/tmp/export_updates_{tag}'
    os.makedirs(base_temp_dir, exist_ok=True)
    
    # Create a folder named after the tag
    tag_dir = os.path.join(base_temp_dir, tag)
    os.makedirs(tag_dir, exist_ok=True)

    # Track used folder names to handle duplicates
    folder_counts = defaultdict(int)
    
    # Populate the tag directory with artwork update subfolders
    for update in updates:
        # Base subfolder name is the artwork's current title
        base_folder_name = update.artwork.title.replace('/', '_').replace('\\', '_')
        folder_counts[base_folder_name] += 1
        
        # Append a number if the title is duplicated
        if folder_counts[base_folder_name] > 1:
            folder_name = f"{base_folder_name}-{folder_counts[base_folder_name] - 1}"
        else:
            folder_name = base_folder_name
        
        # Create the artwork update subfolder
        update_dir = os.path.join(tag_dir, folder_name)
        os.makedirs(update_dir, exist_ok=True)
        
        # Copy the current artwork image
        image_src = os.path.join(current_app.root_path, 'static', update.artwork.image_path)
        image_dst = os.path.join(update_dir, os.path.basename(update.artwork.image_path))
        shutil.copyfile(image_src, image_dst)
        
        # Create an info.txt file with current and proposed changes
        text_file_path = os.path.join(update_dir, 'info.txt')
        with open(text_file_path, 'w') as f:
            f.write(f'ID: {update.artwork.id}\n')
            f.write(f'Current Title: {update.artwork.title}\n')
            f.write(f'Proposed Title: {update.proposed_title or "No Change"}\n')
            f.write(f'Current Description: {update.artwork.description if update.artwork.description else "N/A"}\n')
            f.write(f'Proposed Description: {update.proposed_description or "No Change"}\n')
            f.write(f'Current Hard Tags: {update.artwork.hard_tags}\n')
            f.write(f'Proposed Hard Tags: {update.proposed_hard_tags or "No Change"}\n')
            f.write(f'Current Soft Tags: {update.artwork.soft_tags if update.artwork.soft_tags else "N/A"}\n')
            f.write(f'Proposed Soft Tags: {update.proposed_soft_tags or "No Change"}\n')
            f.write(f'Current Manufacturing Specs: {update.artwork.manufacturing_specs if update.artwork.manufacturing_specs else "N/A"}\n')
            f.write(f'Proposed Manufacturing Specs: {update.proposed_manufacturing_specs or "No Change"}\n')

    # Create the checklist CSV file in the tag directory
    checklist_path = os.path.join(tag_dir, 'checklist.csv')
    with open(checklist_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Artwork ID', 'Title', 'Approve/Disapprove', 'Detail'])
        for update in updates:
            writer.writerow([update.artwork.id, update.artwork.title, '', ''])

    # Create a zip file from the base directory
    zip_path = f'/tmp/artwork_updates_{tag}.zip'
    shutil.make_archive(zip_path.replace('.zip', ''), 'zip', base_temp_dir)
    
    # Send the zip file to the user
    response = send_file(
        zip_path,
        as_attachment=True,
        download_name=f'artwork_updates_{tag}.zip'
    )
    
    # Clean up temporary files (optional, uncomment for production)
    # shutil.rmtree(base_temp_dir)
    # os.remove(zip_path)
    
    return response




@admin_interface.route('/pick_artwork_update/<uuid6:update_id>', methods=['POST'])
@admin_required('artwork_approval_admin')
def pick_artwork_update(admin_id, update_id):

    update = ArtworkUpdate.query.get_or_404(update_id)

    if update.picked_by_admin_id:
        flash("This update has already been picked by another admin.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    # Assign the update to the current admin
    update.picked_by_admin_id = admin_id
    db.session.commit()

    flash(f"Update for artwork '{update.artwork.title}' has been added to your workspace.")
    return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))




@admin_interface.route('/unpick_artwork_update/<uuid6:update_id>', methods=['POST'])
@admin_required('artwork_approval_admin')
def unpick_artwork_update(admin_id, update_id):

    update = ArtworkUpdate.query.get_or_404(update_id)

    if update.picked_by_admin_id != admin_id:
        flash("You can only unpick updates from your own workspace.")
        return redirect(url_for('admin_interface.artwork_update_workspace'))

    # Unassign the update
    update.picked_by_admin_id = None
    db.session.commit()

    flash(f"Update for artwork '{update.artwork.title}' has been removed from your workspace.")
    return redirect(url_for('admin_interface.artwork_update_workspace'))




@admin_interface.route('/approve_update_tag/<uuid6:update_id>/<tag>', methods=['POST'])
@admin_required('artwork_approval_admin')
def approve_update_tag(admin_id, update_id, tag):
    update = ArtworkUpdate.query.get_or_404(update_id)
    
    # Check if the update is still pending
    if update.status != 'Pending':
        flash("This update is not pending approval.")
        return redirect(url_for('admin_interface.artwork_update_workspace'))

    # Normalize the tag to match how it’s stored
    normalized_tag = tag.strip().lower()
    if normalized_tag in update.tag_approvals and update.tag_approvals[normalized_tag] == "Pending":
        # Update the tag approval status
        update.tag_approvals = dict(update.tag_approvals)  # Ensure SQLAlchemy detects the change
        update.tag_approvals[normalized_tag] = "Approved"
        
        # Check if all tags are now approved
        all_approved = all(status == "Approved" for status in update.tag_approvals.values())
        
        if all_approved:
            # Apply the update to the artwork
            artwork = update.artwork
            if update.proposed_title:
                artwork.title = update.proposed_title
            if update.proposed_description:
                artwork.description = update.proposed_description
            if update.proposed_manufacturing_specs:
                artwork.manufacturing_specs = update.proposed_manufacturing_specs
            if update.proposed_hard_tags:
                artwork.hard_tags = update.proposed_hard_tags
            if update.proposed_soft_tags:
                artwork.soft_tags = update.proposed_soft_tags
            
            # Mark the update as approved
            update.status = "Approved"
            update.approval_admin_id = admin_id
            update.reviewed_at = datetime.now()

            update_artwork_timestamp(artwork, commit=False)
            
            # Send a notification to the artist
            artist_id = artwork.artist_id
            message = f"Your artwork '{artwork.title}' has been updated."
            Notification.send_notification(user_id=artist_id, message=message, type='artwork')
            
            flash(f"All tags approved. Update for artwork '{artwork.title}' has been applied.", "success")
        else:
            flash(f"Tag '{tag}' approved for update to '{update.artwork.title}'.", "success")
        
        # Commit the changes to the database
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Error approving tag or applying update: {str(e)}", "error")
    else:
        flash(f"Tag '{tag}' cannot be approved.", "warning")

    return redirect(url_for('admin_interface.artwork_update_workspace'))



@admin_interface.route('/approve_artwork_update/<uuid6:update_id>', methods=['POST'])  # Adjusted uuid6 to uuid
@admin_required('artwork_approval_admin')
def approve_artwork_update(admin_id, update_id):
    update = ArtworkUpdate.query.get_or_404(update_id)

    if update.status != 'Pending':
        flash("Invalid update or it is not pending approval.")
        return redirect(url_for('admin_interface.artwork_update_workspace'))


    # Apply the update to the artwork
    artwork = update.artwork
    if update.proposed_title:
        artwork.title = update.proposed_title
    if update.proposed_description:
        artwork.description = update.proposed_description
    if update.proposed_manufacturing_specs:
        artwork.manufacturing_specs = update.proposed_manufacturing_specs
    if update.proposed_hard_tags:
        artwork.hard_tags = update.proposed_hard_tags
    if update.proposed_soft_tags:
        artwork.soft_tags = update.proposed_soft_tags

    update.status = 'Approved'
    update.approval_admin_id = admin_id
    update.reviewed_at = datetime.now()

    update_artwork_timestamp(artwork, commit=False)

    try:
        db.session.commit()
        flash(f"Update for artwork '{artwork.title}' has been approved.", "success")
        Notification.send_notification(
            user_id=artwork.artist_id,
            message=f"Your artwork '{artwork.title}' has been updated.",
            type='artwork'
        )
    except Exception as e:
        db.session.rollback()
        flash(f"Error approving update: {str(e)}", "error")

    return redirect(url_for('admin_interface.artwork_update_workspace'))


@admin_interface.route('/disapprove_artwork_update/<uuid6:update_id>', methods=['GET', 'POST'])
@admin_required('artwork_approval_admin')
def disapprove_artwork_update(admin_id, update_id):

    # Retrieve the update
    update = ArtworkUpdate.query.get_or_404(update_id)

    if request.method == 'POST':
        reason = request.form.get('disapprove_reason', None)
        
        if reason:
            # Clean the reason by removing HTML tags
            clean_reason = re.sub(r'<[^>]+>', '', html.unescape(reason))
            # Update the status and other details
            update.status = 'Disapproved'
            update.disapproval_reason = clean_reason
            update.approval_admin_id = admin_id
            update.reviewed_at = datetime.now()

            db.session.commit()

            artwork = Artwork.query.get(update.artwork_id)
            update_artwork_timestamp(artwork, commit=True)
            
            
            # Send notification to the artist on the reason
            artist_id = update.artist_id
            message = f"Your artwork update for '{update.artwork.title}' has been disapproved. Reason: {clean_reason}"
            Notification.send_notification(user_id=artist_id, message=message, type='artwork_update')

            flash(f"Update for artwork '{update.artwork.title}' has been disapproved.")
            return redirect(url_for('admin_interface.artwork_update_workspace'))
        else:
            flash("Please provide a reason for disapproval.")

    return render_template('admin/artwork_approval_admin/disapprove_artwork_update.html', update=update)




@admin_interface.route('/search_updates', methods=['GET', 'POST'])
@admin_required('artwork_approval_admin')
def search_updates(admin_id):

    search_query = request.args.get('search_query', '').strip()

    if not search_query:
        flash("Please enter a search query.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    # Fetch search results for updates
    search_results = ArtworkUpdate.query.filter(
        ArtworkUpdate.status == 'Pending',
        ArtworkUpdate.approval_admin_id == None,
        ArtworkUpdate.proposed_hard_tags.ilike(f"%{search_query}%")
    ).all()

    if request.method == 'POST':
        # Handle "Pick All Updates"
        for update in search_results:
            if not update.approval_admin_id:
                update.approval_admin_id = admin_id
        db.session.commit()
        flash("All updates in the search results have been picked.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    return render_template(
        'admin/artwork_approval_admin/search_updates.html',
        search_results=search_results,
        search_query=search_query
    )




# production round admin dashboard, update product status


@admin_interface.route('/production_round_admin_dashboard/<category>', methods=['GET'])
@admin_required('production_round_admin')
def production_round_admin_dashboard(category, admin_id):

    unread_notifications_count = Notification.get_unread_notifications_count(admin_id)

    # Fetch products assigned to the admin
    products = Product.query.filter_by(assigned_admin_id=admin_id).all()

    products_with_active_rounds = {}

    # Categorize products
    active_products = []
    platform_controlled_products = []
    customer_controlled_products = []

    for product in products:
        active_round = ProductionRound.query.filter_by(product_id=product.id, is_active=True).first()

        if active_round:
            active_products.append(product)
            products_with_active_rounds[product.id] = {
                "round": active_round,
                "is_published": active_round.is_published,
                "total_items_ordered": active_round.total_items_ordered,
                "artwork_image": product.image_path if product.image_path else product.artwork.image_path
            }
        else:
            if product.artist_controlled:
                customer_controlled_products.append(product)
            else:
                platform_controlled_products.append(product)

    # Determine which category to render
    if category == "active":
        products_to_display = active_products
    elif category == "platform":
        products_to_display = platform_controlled_products
    elif category == "customer":
        products_to_display = customer_controlled_products
    else:
        flash("Invalid category selected.")
        return redirect(url_for('admin_interface.production_round_admin_dashboard', category="active"))


    # Query for production rounds that might trigger the red dot
    overdue_rounds = ProductionRound.query.filter(
        ProductionRound.admin_id == admin_id,
        ProductionRound.is_published == True,
        ProductionRound.stage == "waiting",
        ProductionRound.max_waiting_time <= datetime.now()
    ).count()

    has_overdue = overdue_rounds > 0


    return render_template(
        'admin/production_round_admin/production_round_admin_dashboard.html',
        category=category,
        products=products_to_display,
        products_with_active_rounds=products_with_active_rounds,
        unread_notifications_count=unread_notifications_count,
        has_overdue=has_overdue  # Pass whether there are overdue rounds
    )






@admin_interface.route('/production_round_calendar', methods=['GET'])
@admin_required('production_round_admin')
def production_round_calendar(admin_id):

    # Query production rounds for the logged-in admin with conditions, sorted by max_waiting_time
    waiting_rounds = ProductionRound.query.filter(
        ProductionRound.admin_id == admin_id,
        ProductionRound.is_published == True,
        ProductionRound.stage == "waiting"
    ).join(Product).order_by(ProductionRound.max_waiting_time.asc()).all()  # Sort ascending by max_waiting_time

    current_date = datetime.now().date()  # Current date for comparison

    return render_template(
        'admin/production_round_admin/production_round_calendar.html',
        waiting_rounds=waiting_rounds,
        current_date=current_date
    )




# the product management: information (manage_product) and display status (toggle_product_display_status)


@admin_interface.route('/manage_product/<uuid6:product_id>', methods=['GET', 'POST'])
@admin_required('production_round_admin')
def manage_product(admin_id, product_id):
    product = Product.query.get(product_id)
    if not product:
        flash("Product not found.", 'error')
        return redirect(url_for('admin_interface.production_round_admin_dashboard', category="active"))

    flash_message = None

    if request.method == 'POST':
        if 'toggle_display_status' in request.form:
            product.toggle_display_status()
            flash_message = f"Display status for '{product.name}' updated to '{product.display_status}'."
        elif 'update_introduction' in request.form:
            introduction = request.form.get('introduction', '').strip()
            if introduction:
                product.introduction = introduction
                db.session.commit()
                flash_message = "Introduction successfully uploaded."
            else:
                flash_message = "Introduction cannot be empty."
        elif 'update_trigger_threshold' in request.form:
            try:
                new_threshold = int(request.form.get('trigger_threshold', '').strip())
                if new_threshold < 1:
                    flash_message = "Trigger threshold must be a positive integer."
                else:
                    product.trigger_threshold = new_threshold
                    db.session.commit()
                    flash_message = f"Trigger threshold for '{product.name}' updated to {new_threshold}."
            except ValueError:
                flash_message = "Trigger threshold must be a valid integer."
        elif 'update_image' in request.form:
            if 'image' in request.files:
                file = request.files['image']
                if file and allowed_image(file.filename):
                    # Generate a unique filename using the product ID
                    extension = file.filename.rsplit('.', 1)[1].lower()
                    filename = f"product_{product.id}.{extension}"
                    file_path = os.path.join(current_app.config['PRODUCT_UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    product.image_path = f'product_images/{filename}'
                    db.session.commit()
                    flash_message = "Product image updated successfully."
                else:
                    flash_message = "Invalid file type. Allowed types: jpg, jpeg, png."
            else:
                flash_message = "No file selected."

    return render_template(
        'admin/production_round_admin/manage_product.html',
        product=product,
        flash_message=flash_message
    )



@admin_interface.route('/toggle_product_display_status/<uuid6:product_id>', methods=['POST'])
@admin_required('production_round_admin')
def toggle_product_display_status(admin_id, product_id):

    product = Product.query.get(product_id)

    # Ensure the product exists and is in an approved state
    if product and product.production_status == 'Approved':
        product.toggle_display_status()
        flash(f"Display status for '{product.name}' updated to '{product.display_status}'.")
    else:
        flash("Invalid product or product is not approved.", "error")

    return redirect(url_for('admin_interface.manage_product', product_id=product.id))



# the production management: initialize production round if the artist choose so (admin_manage_production_round)
# manage production round's information (manage_production_round), display status (publish_production_round)

@admin_interface.route('/admin_initialize_production_round/<uuid6:product_id>', methods=['POST'])
@admin_required('production_round_admin')
def admin_initialize_production_round(admin_id, product_id):

    """Admin initializes a production round."""

    try:
        product = Product.query.get_or_404(product_id)
        if product.assigned_admin_id != admin_id:
            flash("Unauthorized access to this product.")
            return redirect(url_for('admin_interface.admin_dashboard'))

        if product.artist_controlled:
            flash("Production round initialization is controlled by the artist.")
            return redirect(url_for('admin_interface.admin_dashboard'))

        # Check if an active production round already exists
        existing_round = ProductionRound.query.filter_by(product_id=product.id, is_active=True).first()
        if existing_round:
            flash("An in-progress production round already exists. You cannot initialize a new one.")
            return redirect(url_for('admin_interface.admin_manage_production_round', product_id=product.id))

        # Create a new production round
        max_waiting_time_days = 60  # Default waiting period in days
        max_waiting_time = datetime.now() + timedelta(days=max_waiting_time_days)

        new_round = ProductionRound(
            product_id=product.id,
            artist_id=product.artist_id,
            admin_id=admin_id,
            max_waiting_time=max_waiting_time,
            stage="initialize",
            is_published=False,
            is_active=True,  # Set the new round as active
            created_at=datetime.now(),
            updated_at=datetime.now()   # Explicit initialization (optional)
        )
        db.session.add(new_round)
        db.session.commit()

        artwork = Artwork.query.get(product.artwork_id)
        update_artwork_timestamp(artwork, commit=True)

        flash("Production round initialized successfully.")
        return redirect(url_for('admin_interface.admin_manage_production_round', product_id=product.id))

    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'error')
        return redirect(url_for('admin_interface.admin_dashboard'))


# the admin would manage the initialized production round
# there would be a confirmation page, after confirmation, it will be updated


@admin_interface.route('/admin_manage_production_round/<uuid6:product_id>', methods=['GET', 'POST'])
@admin_required('production_round_admin')
def admin_manage_production_round(admin_id, product_id):
    try:
        # Fetch the active production round
        production_round = ProductionRound.query.filter_by(product_id=product_id, is_active=True).first()

        if not production_round:
            flash("No active production round found for this product.")
            return redirect(url_for('admin_interface.production_round_admin_dashboard', category="active"))

        # Get stage goals
        stage_goals = production_round.stage_goals

        if request.method == 'POST':
            # Collect updated data
            updated_data = {
                'price': float(request.form.get('price', production_round.price)),
                'min_production_size': int(request.form.get('min_production_size', production_round.min_production_size)),
                'delivery_point': int(request.form.get('delivery_point', production_round.delivery_point)),
                'max_waiting_time': datetime.strptime(request.form.get('max_waiting_time'), '%Y-%m-%d'),
                'stage': request.form.get('stage', production_round.stage),
                'is_published': 'is_published' in request.form,
                'stage_goals': request.form.get('stage_goals', '[]'),  # Leave raw JSON string
            }

            # Handle stage-specific fields
            if updated_data['stage'] == 'waiting':
                updated_data['partial_refund'] = float(request.form.get('partial_refund', production_round.partial_refund or 0))
                updated_data['sample_fee'] = float(request.form.get('sample_fee', production_round.sample_fee or 0))
                updated_data['artist_payout_percentage'] = float(request.form.get('artist_payout_percentage', production_round.artist_payout_percentage or 0))
            
            if updated_data['stage'] == 'production':
                updated_data['mass_production_fee'] = float(request.form.get('mass_production_fee', production_round.mass_production_fee or 0))

            # Serialize stage goals and store in session
            try:
                updated_data['stage_goals'] = json.loads(updated_data['stage_goals'])
            except Exception as e:
                updated_data['stage_goals'] = []

            session['pending_updates'] = updated_data
            session['round_id'] = str(production_round.id)
            return redirect(url_for('admin_interface.confirm_production_round_update'))

        # Render the management page
        return render_template(
            'admin/production_round_admin/admin_manage_production_round.html',
            production_round=production_round,
            stage_goals=stage_goals,
        )

    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'error')
        return redirect(url_for('admin_interface.admin_login'))


@admin_interface.route('/confirm_production_round_update', methods=['GET', 'POST'])
@admin_required('production_round_admin')
def confirm_production_round_update(admin_id):
    try:
        # Fetch data from session
        round_id = session.get('round_id')
        updated_data = session.get('pending_updates')

        if not round_id or not updated_data:
            flash("No updates to confirm.")
            return redirect(url_for('admin_interface.production_round_admin_dashboard', category="active"))

        production_round = ProductionRound.query.get(uuid.UUID(round_id))
        if not production_round:
            flash("Production round not found.")
            return redirect(url_for('admin_interface.production_round_admin_dashboard', category="active"))

        # Fetch the associated product
        product = production_round.product
        if not product:
            flash("Associated product not found for this production round.", "error")
            return redirect(url_for('admin_interface.production_round_admin_dashboard', category="active"))

        # Normalize and validate stage goals
        raw_stage_goals = updated_data.get('stage_goals', [])
        normalized_stage_goals = [
            {
                'quantity': goal.get('quantity') or goal.get('target_quantity'),
                'gift': goal.get('gift')
            }
            for goal in raw_stage_goals
        ]
        for goal in normalized_stage_goals:
            if 'quantity' not in goal or 'gift' not in goal:
                raise ValueError("Each goal must include 'quantity' and 'gift' keys.")
            if not isinstance(goal['quantity'], int) or goal['quantity'] <= 0:
                raise ValueError(f"Invalid quantity in stage goal: {goal}")

        if request.method == 'POST':
            # Update production round fields
            production_round.admin_id = admin_id
            production_round.price = updated_data['price']
            production_round.min_production_size = updated_data['min_production_size']
            production_round.delivery_point = updated_data['delivery_point']
            production_round.max_waiting_time = updated_data['max_waiting_time']
            production_round.stage = updated_data['stage']
            production_round.is_published = updated_data['is_published']
            production_round.is_active = updated_data['stage'] in ["initialize", "waiting", "sample", "production", "examination"]
            production_round.stage_goals = normalized_stage_goals

            # Stage-specific updates and transactions
            if updated_data['stage'] == 'waiting':
                # Validate and update sample-specific fields
                if 'partial_refund' not in updated_data or updated_data['partial_refund'] < 0:
                    flash("Partial refund amount must be a positive value.")
                    return redirect(url_for('admin_interface.confirm_production_round_update'))
                if 'sample_fee' not in updated_data or updated_data['sample_fee'] < 0:
                    flash("Sample fee must be a positive value.")
                    return redirect(url_for('admin_interface.confirm_production_round_update'))
                if 'artist_payout_percentage' not in updated_data or not (0 <= updated_data['artist_payout_percentage'] <= 100):
                    flash("Artist payout percentage must be between 0 and 100.")
                    return redirect(url_for('admin_interface.confirm_production_round_update'))

                production_round.partial_refund = updated_data['partial_refund']
                production_round.sample_fee = updated_data['sample_fee']
                production_round.artist_payout_percentage = updated_data['artist_payout_percentage']
                
            elif updated_data['stage'] == 'sample':
                # Create AccountingTransaction for sample fee
                AccountingTransaction.initiate_transaction("factory_sample_payment", production_round.sample_fee, production_round.id)

            elif updated_data['stage'] == 'production':
                # Validate and update production-specific field
                if 'mass_production_fee' not in updated_data or updated_data['mass_production_fee'] < 0:
                    flash("Mass production fee must be a positive value.")
                    return redirect(url_for('admin_interface.confirm_production_round_update'))

                production_round.mass_production_fee = updated_data['mass_production_fee']
                # Create AccountingTransaction for mass production fee
                AccountingTransaction.initiate_transaction("factory_production_payment", production_round.mass_production_fee, production_round.id)

            elif updated_data['stage'] == 'stocking':
                # Ensure artist_payout_percentage is set (likely from sample stage)
                if production_round.artist_payout_percentage is None:
                    flash("Artist payout percentage must be set before stocking stage.")
                    return redirect(url_for('admin_interface.confirm_production_round_update'))
                # Calculate artist payout amount
                artist_payout_amount = (production_round.artist_payout_percentage / 100) * production_round.price * production_round.total_items_ordered
                # Create AccountingTransaction for artist payout
                transaction = AccountingTransaction.initiate_transaction("artist_payout", artist_payout_amount, production_round.id)
                # Create Payout record linked to the transaction
                payout = Payout(
                    artist_id=production_round.artist_id,
                    production_round_id=production_round.id,
                    total_amount=artist_payout_amount,
                    status="pending",
                    accounting_transaction_id=transaction.id
                )
                db.session.add(payout)

            artwork = Artwork.query.get(production_round.product.artwork_id)
            update_artwork_timestamp(artwork, commit=False)

            # Commit all changes
            db.session.commit()

            # Notify customers if stage is "waiting"
            if updated_data['stage'] == "waiting":
                try:
                    product.notify_customers_on_waiting_round()
                    db.session.commit()
                    logging.info(f"Notified customers for waiting round of product {product.name} (ID: {product.id})")
                except Exception as e:
                    db.session.rollback()
                    logging.error(f"Failed to notify customers for waiting round: {str(e)}")
                    flash(f"Production round updated, but customer notifications failed: {str(e)}", "warning")

            # Inline refund logic for "abandon" stage (unchanged from original)
            if updated_data['stage'] == "abandon":
                logging.info(f"Detected 'abandon' stage for round {round_id}. Starting refund process.")
                if production_round.price is None:
                    logging.warning(f"No price set for round {round_id}. Skipping refunds.")
                    flash("Cannot process refunds: No price set.", "warning")
                else:
                    items_to_refund = ItemOrderItem.query.filter_by(
                        production_round_id=production_round.id,
                        item_status="item"
                    ).all()
                    logging.info(f"Found {len(items_to_refund)} items with status 'item' for refund.")

                    if not items_to_refund:
                        logging.info("No items to refund.")
                        flash("No eligible items to refund.", "info")
                    else:
                        refund_records = []
                        for item in items_to_refund:
                            if not item.item_order or not item.item_order.customer_id:
                                logging.error(f"Item {item.id} has no valid order or customer.")
                                continue
                            if not item.region or item.region.tax_rate is None:
                                logging.error(f"Item {item.id} has no valid region or tax rate.")
                                continue

                            customer_id = item.item_order.customer_id
                            refund_amount = production_round.price * (item.region.tax_rate + 1)
                            logging.debug(f"Refunding item {item.id} for customer {customer_id}: {refund_amount}")

                            refund_order = RefundItemOrder(
                                customer_id=customer_id,
                                item_order_item_id=item.id,
                                refund_amount=refund_amount,
                                is_auto=True,
                                reason="Production round abandoned",
                                refund_method="wallet",
                                refund_status="processed",
                                refund_timestamp=datetime.now()
                            )
                            refund_records.append(refund_order)
                            item.item_status = "refunded"

                        if refund_records:
                            db.session.add_all(refund_records)
                            db.session.commit()
                            logging.info(f"Created {len(refund_records)} refund records.")

                            refunds_by_customer = defaultdict(float)
                            for refund in refund_records:
                                refunds_by_customer[refund.customer_id] += refund.refund_amount

                            for customer_id, total_refund in refunds_by_customer.items():
                                customer = Customer.query.get(customer_id)
                                if not customer:
                                    logging.error(f"Customer {customer_id} not found.")
                                    continue
                                old_balance = customer.wallet_balance
                                customer.wallet_balance += total_refund
                                logging.info(f"Updated wallet for {customer_id}: {old_balance} -> {customer.wallet_balance}")

                                message = f"Refund of {total_refund:.2f} issued for {product.name} due to abandonment."
                                Notification.send_notification(
                                    user_id=customer_id,
                                    message=message,
                                    type="refund"
                                )
                            db.session.commit()
                            logging.info("Refund process completed successfully.")
                            flash(f"Refunded {len(refund_records)} items successfully.", "success")
                        else:
                            logging.warning("No valid refunds processed.")
                            flash("No valid items refunded due to data issues.", "warning")

            # Notify customers of stage update
            notifications = ProductionRoundNotification.query.filter_by(production_round_id=production_round.id).all()
            for notification in notifications:
                Notification.send_notification(
                    user_id=notification.customer_id,
                    message=f"The production round of {product.name} has been updated to {production_round.stage}.",
                    type="production_round_update"
                )

            # Clear session data
            session.pop('pending_updates', None)
            session.pop('round_id', None)
            flash("Production round updates confirmed and notifications sent.")
            return redirect(url_for('admin_interface.production_round_admin_dashboard', category="active"))

        # Render confirmation page
        return render_template(
            'admin/production_round_admin/confirm_production_round_update.html',
            production_round=production_round,
            updated_data=updated_data,
        )
    except Exception as e:
        logging.error(f"Error in confirm_production_round_update: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for('admin_interface.admin_login'))






@admin_interface.route('/publish_production_round/<uuid6:round_id>', methods=['POST'])
@admin_required('production_round_admin')
def publish_production_round(admin_id, round_id):
    """Toggle display status for the production round."""

    production_round = ProductionRound.query.get(round_id)
    if not production_round or production_round.admin_id != admin_id:
        flash("Unauthorized access or invalid production round.")
        return redirect(url_for('admin_interface.production_round_admin_dashboard', category= "active"))

    production_round.is_published = not production_round.is_published
    db.session.commit()

    flash(f"Production round for product '{production_round.product.name}' display status updated.")
    return redirect(url_for('admin_interface.production_round_admin_dashboard', category= "active"))




# create additional accounting transaction (error handling and production stage goal

@admin_interface.route('/create_accounting_transaction/<uuid6:round_id>', methods=['GET', 'POST'])
@admin_required('production_round_admin')
def create_accounting_transaction(admin_id, round_id):
    production_round = ProductionRound.query.get_or_404(round_id)
    
    if request.method == 'POST':
        transaction_type = request.form.get('transaction_type')
        amount = float(request.form.get('amount'))
        
        # Validate inputs
        valid_transaction_types = [
            'artist_payout', 
            'factory_sample_payment', 
            'factory_production_payment', 
            'factory_stage_goal_payment'
        ]
        
        if transaction_type not in valid_transaction_types:
            flash('Invalid transaction type', 'error')
            return redirect(request.url)
        
        if amount <= 0:
            flash('Amount must be greater than zero', 'error')
            return redirect(request.url)
            
        # Create the transaction
        transaction = AccountingTransaction.initiate_transaction(
            transaction_type=transaction_type,
            amount=amount,
            production_round_id=round_id
        )
        
        flash('Accounting transaction created successfully', 'success')
        return redirect(url_for('admin_interface.create_accounting_transaction', round_id=round_id))
    
    return render_template(
        'admin/production_round_admin/create_accounting_transaction.html',
        production_round=production_round
    )







@admin_interface.route('/send_custom_message/<uuid6:round_id>', methods=['GET', 'POST'])
@admin_required('production_round_admin')
def send_custom_message(admin_id, round_id):
    try:
        # Query directly with round_id (UUID object)
        production_round = ProductionRound.query.get(round_id)
        if not production_round:
            flash("Production round not found.")
            return redirect(url_for('admin_interface.production_round_admin_dashboard', category= "active"))

        if request.method == 'POST':
            custom_message = request.form.get('custom_message', '').strip()
            if not custom_message:
                flash("Message cannot be empty.", "error")
                return redirect(url_for('admin_interface.send_custom_message', round_id=round_id))

            # Send notification to all customers in the notification list
            notifications = ProductionRoundNotification.query.filter_by(production_round_id=round_id).all()
            for notification in notifications:
                Notification.send_notification(
                    user_id=notification.customer_id,
                    message=custom_message,
                    type="admin_message"
                )

            flash("Custom message has been sent to all customers in the notification list.", "success")
            return redirect(url_for('admin_interface.production_round_admin_dashboard', category= "active"))

        return render_template(
            'admin/production_round_admin/send_custom_message.html',
            production_round=production_round
        )
    except Exception as e:
        logging.error(f"An error occurred in send_custom_message: {e}")
        flash(f"An error occurred: {str(e)}", 'error')
        return redirect(url_for('admin_interface.admin_login'))



# archived information for a production round: information and dialog

@admin_interface.route('/archived_production_rounds/<uuid6:product_id>', methods=['GET'])
@admin_required('production_round_admin')
def archived_production_rounds(admin_id, product_id):
    """List all inactive production rounds for a specific product."""
    product = Product.query.get(product_id)
    if not product:
        flash("Product not found.")
        return redirect(url_for('admin_interface.production_round_admin_dashboard', category= "active"))

    # Fetch all inactive production rounds for the product
    inactive_rounds = (
        ProductionRound.query.filter_by(product_id=product_id, is_active=False)
        .order_by(ProductionRound.created_at.desc())
        .all()
    )

    return render_template(
        'admin/production_round_admin/archived_production_rounds.html',
        product=product,
        inactive_rounds=inactive_rounds,
    )





@admin_interface.route('/archived_production_round_dialogs/<uuid6:round_id>', methods=['GET'])
@admin_required('production_round_admin')
def archived_production_round_dialogs(admin_id, round_id):
    """View archived dialogs of a specific production round."""
    production_round = ProductionRound.query.get(round_id)
    if not production_round or production_round.is_active:
        flash("Invalid or active production round.")
        return redirect(url_for('admin_interface.production_round_admin_dashboard', category= "active"))

    dialogs = production_round.dialogs  # Retrieve all dialogs for the production round

    # Attach files to each dialog for display
    for dialog in dialogs:
        dialog.files_list = dialog.files  # Collect related files

    return render_template(
        'admin/production_round_admin/archived_production_round_dialogs.html',
        production_round=production_round,
        dialogs=dialogs,
    )




@admin_interface.route('/archived_production_round_details/<uuid6:round_id>', methods=['GET'])
@admin_required('production_round_admin')
def archived_production_round_details(admin_id, round_id):
    """View detailed information about an archived production round."""
    production_round = ProductionRound.query.get(round_id)
    if not production_round or production_round.is_active:
        flash("Invalid or active production round.")
        return redirect(url_for('admin_interface.production_round_admin_dashboard', category= "active"))

    # Extract stage goals (assuming JSON format)
    stage_goals = json.loads(production_round.production_goals or "[]")

    return render_template(
        'admin/production_round_admin/archived_production_round_details.html',
        production_round=production_round,
        stage_goals=stage_goals,
    )




# initialize a request to trasfer the management control to other production_round_admin
# the request would be pick and approved by product_approval_admin
# the ProductManageTransferRequest is going to record the information for operation and history


@admin_interface.route('/initiate_product_transfer', methods=['GET', 'POST'])
@admin_required('production_round_admin')
def initiate_product_transfer(admin_id):

    # Get search query from request arguments
    search_query = request.args.get('search_query', '').strip()

    # Subquery to filter out products with a "Pending" ProductManageTransferRequest
    excluded_products = db.session.query(ProductManageTransferRequest.product_id).filter_by(status='Pending')

    # Base query to filter products managed by the current admin and not in excluded_products
    query = Product.query.filter(
        Product.assigned_admin_id == admin_id,
        ~Product.id.in_(excluded_products)
    )

    # Apply search query if provided
    if search_query:
        query = query.filter(
            db.or_(
                cast(Product.id, String).ilike(f"%{search_query}%"),
                Product.name.ilike(f"%{search_query}%"),
                cast(Product.artist_id, String).ilike(f"%{search_query}%"),
                Product.production_specs.ilike(f"%{search_query}%")
            )
        )
    products = query.all()

    if request.method == 'POST':
        product_id = request.form.get('product_id')
        reason = request.form.get('reason')
        if product_id and reason:
            transfer_request = ProductManageTransferRequest(
                product_id=uuid.UUID(product_id),
                current_admin_id=admin_id,
                reason=reason,
                status='Pending',
                submitted_at=datetime.now()
            )
            db.session.add(transfer_request)
            db.session.commit()
            flash("Transfer request has been submitted.")
            return redirect(url_for('admin_interface.initiate_product_transfer'))
        else:
            flash("Please select a product and provide a reason.")

    return render_template(
        'admin/production_round_admin/initiate_product_transfer.html',
        products=products,
        search_query=search_query
    )




# Product Approval Admin Dashboard: approve product; approve product management transfer
# download design file, approve product, disapprove product, assign product to order management admin
# product management transfer from production_round_admin

@admin_interface.route('/product_approval_admin_dashboard', methods=['GET', 'POST'])
@admin_required('product_approval_admin')
def product_approval_admin_dashboard(admin_id):

    search_query = request.args.get('search_query', '').strip()

    # Fetch all pending products that are not picked by any admin
    pending_products = Product.query.filter_by(production_status='Pending', picked_by_admin_id=None).all()

    # Fetch all pending product transfer requests not picked by any admin
    pending_transfer_requests = ProductManageTransferRequest.query.filter_by(
        status='Pending', picked_by_admin_id=None
    ).all()

    # Filter products based on the search query
    search_results = []
    if search_query:
        search_results = Product.query.filter(
            Product.production_status == 'Pending',
            Product.picked_by_admin_id == None,
            Product.production_specs.ilike(f"%{search_query}%")
        ).all()

    return render_template(
        'admin/product_approval_admin/product_approval_admin_dashboard.html',
        pending_products=pending_products,
        pending_transfer_requests=pending_transfer_requests,
        search_query=search_query,
        search_results=search_results
    )




# approve product and assign production_round_admin

# search function for the manufactual_type, individual pick and pick-all
# product are first picked to the workspace for approval/disapproval
# The picked product is not going to be displayed on the dashboard.


@admin_interface.route('/search_products', methods=['GET', 'POST'])
@admin_required('product_approval_admin')
def search_products(admin_id):

    search_query = request.args.get('search_query', '').strip()

    if not search_query:
        flash("Please enter a search query.")
        return redirect(url_for('admin_interface.product_approval_admin_dashboard'))

    # Fetch search results
    search_results = Product.query.filter(
        Product.production_status == 'Pending',
        Product.picked_by_admin_id == None,
        Product.production_specs.ilike(f"%{search_query}%")
    ).all()

    if request.method == 'POST':
        # Handle "Pick All Products"
        for product in search_results:
            if not product.picked_by_admin_id:
                product.picked_by_admin_id = admin_id
        db.session.commit()
        flash("All products in the search results have been picked.")
        return redirect(url_for('admin_interface.product_approval_admin_dashboard'))

    return render_template(
        'admin/product_approval_admin/search_results.html',
        search_results=search_results,
        search_query=search_query
    )





@admin_interface.route('/pick_product/<uuid6:product_id>', methods=['POST'])
@admin_required('product_approval_admin')
def pick_product(admin_id, product_id):
    product = Product.query.get_or_404(product_id)

    if product.picked_by_admin_id:
        flash("This product has already been picked by another admin.")
    else:
        product.picked_by_admin_id = current_user.id
        db.session.commit()
        flash(f"Product '{product.name}' has been added to your workspace.")

    return redirect(url_for('admin_interface.product_approval_admin_dashboard'))


@admin_interface.route('/unpick_product/<uuid6:product_id>', methods=['POST'])
@admin_required('product_approval_admin')
def unpick_product(admin_id, product_id):
    """Allow the product approval admin to unpick a product."""

    product = Product.query.get_or_404(product_id)

    if product.picked_by_admin_id != admin_id:
        flash("You cannot unpick a product that is not in your workspace.")
    else:
        admin = ProductApprovalAdmin.query.get(admin_id)
        admin.unpick_product(product)
        flash(f"Product '{product.name}' has been removed from your workspace.")

    return redirect(url_for('admin_interface.product_approval_workspace'))


@admin_interface.route('/product_approval_workspace', methods=['GET'])
@admin_required('product_approval_admin')
def product_approval_workspace(admin_id):
    """Display the workspace of the product approval admin."""
    
    # Fetch picked products with associated artwork details
    picked_products = Product.query.filter_by(
        picked_by_admin_id=admin_id,
        production_status='Pending'  # Exclude products that are already approved or disapproved
    ).all()

    # Build detailed product information for rendering
    product_details = []
    for product in picked_products:
        artwork = product.artwork  # Fetch related artwork
        details = {
            "id": product.id,
            "name": product.name,
            "manufacture_type": product.manufacture_type,
            "production_specs": product.production_specs,
            "artist_name": product.artist.name if product.artist else "Unknown",
            "artwork_title": artwork.title if artwork else "No Artwork",
            "artwork_description": artwork.description if artwork else "No Description",
            "artwork_image_path": artwork.image_path if artwork else "No Image",
            "artwork_manufacturing_specs": artwork.manufacturing_specs if artwork else "No Specs",
            "design_files": product.design_files  # Assuming a list of design files
        }
        product_details.append(details)

    return render_template(
        'admin/product_approval_admin/product_approval_workspace.html',
        picked_products=product_details
    )


@admin_interface.route('/approve_product/<uuid6:product_id>', methods=['POST'])
@admin_required('product_approval_admin')
def approve_product(admin_id, product_id):
    """Redirect to assign a Production Round Admin upon approval initiation."""

    # Fetch the product from the database
    product = Product.query.get_or_404(product_id)

    # Ensure the product is in the pending state
    if product.production_status == 'Pending':
        flash(f"Product '{product.name}' approval initiated. Please assign a Production Round Admin.")

        # Redirect to the Order Management Admin assignment page
        return redirect(url_for('admin_interface.assign_production_round_admin', product_id=product.id))
    else:
        flash("Invalid product or it is not pending approval.")

    return redirect(url_for('admin_interface.product_approval_workspace'))




@admin_interface.route('/disapprove_product/<uuid6:product_id>', methods=['GET', 'POST'])
@admin_required('product_approval_admin')
def disapprove_product(admin_id, product_id):
    """Disapprove a product with a reason."""

    # Fetch the product
    product = Product.query.get_or_404(product_id)

    # Ensure the product is pending
    if product.production_status != 'Pending':
        flash("Invalid product or product is not pending.")
        return redirect(url_for('admin_interface.product_approval_admin_dashboard'))

    if request.method == 'POST':
        # Get the disapproval reason
        reason = request.form.get('disapprove_reason')
        
        if reason:
            # Clean the reason by removing HTML tags
            clean_reason = re.sub(r'<[^>]+>', '', html.unescape(reason))
            # Update product status
            product.production_status = 'Disapproved'
            product.disapproval_reason = clean_reason
            db.session.commit()

            artwork = Artwork.query.get(product.artwork_id)
            update_artwork_timestamp(artwork, commit=True)

            # Notify the artist
            artist = product.artist
            if artist:
                message = f"Your product '{product.name}' has been disapproved. Reason: {clean_reason}"
                Notification.send_notification(user_id=artist.id, message=message, type='product')


            flash(f"Product '{product.name}' has been disapproved with reason: {clean_reason}")
            return redirect(url_for('admin_interface.product_approval_workspace'))
        else:
            flash("Disapproval reason is required.")

    # Render the disapproval form on GET requests
    return render_template('admin/product_approval_admin/disapprove_product.html', product=product)



@admin_interface.route('/assign_production_round_admin/<uuid6:product_id>', methods=['GET', 'POST'])
@admin_required('product_approval_admin')
def assign_production_round_admin(admin_id, product_id):
    """Assign an Order Management Admin to an approved product."""

    # Fetch the product
    product = Product.query.get_or_404(product_id)
    if product.production_status != 'Pending':
        flash("Invalid product or product is not ready for admin assignment.")
        return redirect(url_for('admin_interface.product_approval_admin_dashboard'))

    search_criteria = {
        "admin_id": request.form.get("admin_id", "").strip(),
        "name": request.form.get("name", "").strip(),
        "main_production_species": request.form.get("main_production_species", "").strip(),
    }

    # Base query
    query = ProductionRoundAdmin.query

    # Fix: Convert admin_id string to UUID for searching
    if search_criteria["admin_id"]:
        try:
            admin_uuid = uuid.UUID(search_criteria["admin_id"])  # Convert string to UUID
            query = query.filter(ProductionRoundAdmin.id == admin_uuid)
        except ValueError:
            flash("Invalid UUID format for Admin ID.", "danger")

    if search_criteria["name"]:
        query = query.filter(ProductionRoundAdmin.name.ilike(f"%{search_criteria['name']}%"))

    if search_criteria["main_production_species"]:
        query = query.filter(ProductionRoundAdmin.main_production_species.ilike(f"%{search_criteria['main_production_species']}%"))

    production_round_admins = query.all()



    # Sort by the number of products managed
    production_round_admins = query.outerjoin(Product, Product.assigned_admin_id == ProductionRoundAdmin.id) \
                                    .group_by(ProductionRoundAdmin.id) \
                                    .order_by(db.func.count(Product.id).asc()) \
                                    .all()

    if request.method == 'POST' and 'assign' in request.form:
        selected_admin_id = uuid.UUID(request.form.get('selected_admin'))
        if admin_id:
            try:
                selected_admin = ProductionRoundAdmin.query.get(selected_admin_id)
                if selected_admin:
                    product.assigned_admin_id = selected_admin_id
                    product.production_status = 'Approved'
                    
                    Notification.send_notification(
                        user_id=selected_admin_id,
                        message=f"The'{product.name}'has been assigned to you.",
                        type='assign_production_round'
                    )

                    # Notify the artist about the approval initiation
                    Notification.send_notification(
                        user_id=product.artist_id,
                        message=f"Your product '{product.name}' has been marked for approval.",
                        type='product'
                    )

                    artwork = Artwork.query.get(product.artwork_id)
                    update_artwork_timestamp(artwork, commit=False)

                    db.session.commit()

                    flash(f"Product '{product.name}' has been assigned to '{selected_admin.name}' and is now fully approved.")
                    return redirect(url_for('admin_interface.product_approval_workspace'))
                else:
                    flash("Selected Order Management Admin does not exist.")
            except ValueError:
                flash("Invalid Order Management Admin ID format.")

    return render_template(
        'admin/product_approval_admin/assign_production_round_admin.html',
        product=product,
        production_round_admins=production_round_admins,
        search_criteria=search_criteria
    )





@admin_interface.route('/download_file/<uuid6:file_id>')
@admin_required('product_approval_admin')
def download_file(admin_id, file_id):

    design_file = DesignFile.query.get(file_id)
    if not design_file:
        flash("File not found.")
        return redirect(request.referrer or url_for('admin_interface.admin_login'))

    # Construct the full file path
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], design_file.filename)

    # Return the file as an attachment
    return send_file(file_path, as_attachment=True)



# product management trasfer, request sent from order management admin


@admin_interface.route('/pick_transfer_request/<uuid6:request_id>', methods=['POST'])
@admin_required('product_approval_admin')
def pick_transfer_request(admin_id, request_id):

    transfer_request = ProductManageTransferRequest.query.get_or_404(request_id)
    if transfer_request.picked_by_admin_id:
        flash("This request has already been picked by another admin.")
        return redirect(url_for('admin_interface.product_approval_admin_dashboard'))

    transfer_request.picked_by_admin_id = admin_id
    db.session.commit()
    flash("Request has been added to your workspace.")
    return redirect(url_for('admin_interface.product_management_transfer_workspace'))





@admin_interface.route('/product_management_transfer_workspace', methods=['GET'])
@admin_required('product_approval_admin')
def product_management_transfer_workspace(admin_id):

    picked_requests = ProductManageTransferRequest.query.filter_by(
        picked_by_admin_id=admin_id, status='Pending'
    ).all()

    return render_template(
        'admin/product_approval_admin/product_management_transfer_workspace.html',
        picked_requests=picked_requests
    )




@admin_interface.route('/approve_transfer_request/<uuid6:request_id>', methods=['GET', 'POST'])
@admin_required('product_approval_admin')
def approve_transfer_request(admin_id, request_id):

    # Retrieve the transfer request
    transfer_request = ProductManageTransferRequest.query.get_or_404(request_id)
    if transfer_request.status != 'Pending':
        flash("This transfer request is not pending approval.")
        return redirect(url_for('admin_interface.product_management_transfer_workspace'))

    search_query = {
        "admin_id": request.args.get("admin_id", "").strip(),
        "name": request.args.get("name", "").strip(),
        "main_production_species": request.args.get("main_production_species", "").strip(),
    }

    # Base query for filtering ProductionRoundAdmins
    query = ProductionRoundAdmin.query
    if search_query["name"]:
        query = query.filter(ProductionRoundAdmin.name.ilike(f"%{search_query['name']}%"))
    if search_query["main_production_species"]:
        query = query.filter(ProductionRoundAdmin.main_production_species.ilike(f"%{search_query['main_production_species']}%"))

    # Fetch results
    production_round_admins = query.all()

    if request.method == 'POST':
        selected_admin_id = request.form.get("selected_admin")
        if selected_admin_id:
            try:
                selected_admin = ProductionRoundAdmin.query.get(uuid.UUID(selected_admin_id))
                if selected_admin:
                    # Update the product's assigned admin
                    transfer_request.product.assigned_admin_id = selected_admin.id

                    # Mark the transfer request as approved
                    transfer_request.status = 'Approved'
                    transfer_request.reviewed_by = admin_id
                    transfer_request.reviewed_at = datetime.now()

                    db.session.commit()

                    # Notify the current and new admins
                    Notification.send_notification(
                        user_id=transfer_request.current_admin_id,
                        message=f"The transfer request for product '{transfer_request.product.name}' has been approved.",
                        type="product_transfer"
                    )
                    Notification.send_notification(
                        user_id=selected_admin.id,
                        message=f"You have been assigned to manage the product '{transfer_request.product.name}'.",
                        type="product_transfer"
                    )

                    flash(f"Product '{transfer_request.product.name}' has been successfully transferred to '{selected_admin.name}'.")
                    return redirect(url_for('admin_interface.product_management_transfer_workspace'))
                else:
                    flash("Selected admin not found.")
            except ValueError:
                flash("Invalid admin ID format.")

    return render_template(
        'admin/product_approval_admin/approve_transfer_request.html',
        transfer_request=transfer_request,
        production_round_admins=production_round_admins,
        search_query=search_query
    )


@admin_interface.route('/disapprove_transfer_request/<uuid6:request_id>', methods=['GET', 'POST'])
@admin_required('product_approval_admin')
def disapprove_transfer_request(admin_id, request_id):

    transfer_request = ProductManageTransferRequest.query.get_or_404(request_id)

    if request.method == 'POST':
        reason = request.form.get('disapproval_reason')
        if not reason:
            flash("Please provide a reason for disapproval.")
            return render_template(
                'admin/product_approval_admin/disapprove_transfer_request.html',
                transfer_request=transfer_request
            )

        # Disapprove the transfer request
        transfer_request.status = 'Disapproved'
        transfer_request.disapproval_reason = reason
        transfer_request.reviewed_by = admin_id
        transfer_request.reviewed_at = datetime.now()
        db.session.commit()

        # Notify the current admin about disapproval
        Notification.send_notification(
            user_id=transfer_request.current_admin_id,
            message=f"Your transfer request for product '{transfer_request.product.name}' has been disapproved. Reason: {reason}",
            type="product_transfer"
        )

        flash(f"Transfer request for product '{transfer_request.product.name}' has been disapproved.")
        return redirect(url_for('admin_interface.product_management_transfer_workspace'))

    return render_template(
        'admin/product_approval_admin/disapprove_transfer_request.html',
        transfer_request=transfer_request
    )


# warehouse admin section

# warehouse admin dashboard
# choose the production round 

@admin_interface.route('/warehouse_admin/dashboard', methods=['GET', 'POST'])
@admin_required('warehouse_admin')
def warehouse_admin_dashboard(admin_id):
    """WarehouseAdmin dashboard for managing production rounds."""

    production_rounds = []
    search_query = None

    if request.method == 'POST':
        search_query = request.form.get('search_query', '').strip()
        uuid_query = None

        try:
            uuid_query = uuid.UUID(search_query)
        except ValueError:
            uuid_query = None

        if search_query:
            production_rounds = ProductionRound.query.join(Product).filter(
                (ProductionRound.id == uuid_query) |
                (ProductionRound.product_id == uuid_query) |
                (Product.name.ilike(f"%{search_query}%")),
                ProductionRound.stage.in_(["production", "examination", "stocking"])
            ).all()
        else:
            production_rounds = []
    else:
        production_rounds = []

    for round in production_rounds:
        try:
            round.stage_goals = json.loads(round.production_goals) if round.production_goals else []
        except ValueError:
            round.stage_goals = []

    return render_template(
        'admin/warehouse_admin/warehouse_admin_dashboard.html',
        production_rounds=production_rounds,
        search_query=search_query
    )


# Warehouse Storage management: create (single/batch), search & delete empty Storage
@admin_interface.route('/warehouse_admin/storage', methods=['GET', 'POST'])
@admin_required('warehouse_admin')
def warehouse_storage(admin_id):
    """Manage warehouse storage: create new locations and search."""
    warehouses = Warehouse.query.order_by(Warehouse.name).all()

    if request.method == 'POST':
        warehouse_id = request.form.get('warehouse_id')
        aisle_number = request.form.get('aisle_number')
        shelf_number = request.form.get('shelf_number')
        position_number = request.form.get('position_number')
        size = request.form.get('size')

        # Validate all inputs are provided
        if not all([warehouse_id, aisle_number, shelf_number, position_number, size]):
            flash("All fields are required.", "danger")
            return redirect(url_for('admin_interface.warehouse_storage'))

        try:
            # Convert inputs to integers
            warehouse_id = int(warehouse_id)
            aisle_number = int(aisle_number)
            shelf_number = int(shelf_number)
            position_number = int(position_number)
            size = int(size)

            # Check if the warehouse exists
            warehouse = Warehouse.query.get(warehouse_id)
            if not warehouse:
                flash(f"Warehouse ID {warehouse_id} not found.", "danger")
                return redirect(url_for('admin_interface.warehouse_storage'))

            # Generate location_name
            location_name = WarehouseStorage.generate_location_name(
                warehouse_id, aisle_number, shelf_number, position_number
            )

            # Check for duplicate location_name
            if WarehouseStorage.query.get(location_name):
                flash(f"Storage location '{location_name}' already exists.", "danger")
                return redirect(url_for('admin_interface.warehouse_storage'))

            # Create and save new storage
            new_storage = WarehouseStorage(
                location_name=location_name,
                aisle_number=aisle_number,
                shelf_number=shelf_number,
                position_number=position_number,
                size=size,
                warehouse_id=warehouse_id,
                is_available=True
            )
            db.session.add(new_storage)
            db.session.commit()
            logging.debug(f"Created WarehouseStorage: {location_name} in Warehouse {warehouse.name}")
            flash(f"Storage location '{location_name}' created successfully!", "success")

        except ValueError:
            flash("Invalid input. Please ensure all fields are correctly filled.", "danger")
        except Exception as e:
            db.session.rollback()
            logging.exception(f"Error creating WarehouseStorage: {e}")
            flash(f"An error occurred: {e}", "danger")

        return redirect(url_for('admin_interface.warehouse_storage'))

    return render_template('admin/warehouse_admin/warehouse_storage.html', warehouses=warehouses)




@admin_interface.route('/warehouse_admin/batch_create_storage', methods=['GET', 'POST'])
@admin_required('warehouse_admin')
def batch_create_storage(admin_id):
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part in the request.', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            try:
                data = process_file_path(file_path)  # Use the new function
                # Generate location_name for each row
                for row in data:
                    row['location_name'] = WarehouseStorage.generate_location_name(
                        int(row['warehouse_id']),
                        int(row['aisle_number']),
                        int(row['shelf_number']),
                        int(row['position_number'])
                    )
                session['batch_data'] = data
                return redirect(url_for('admin_interface.preview_batch_storage'))
            except Exception as e:
                flash(f'Error processing file: {str(e)}', 'danger')
                return redirect(request.url)
            finally:
                # Optional: Clean up the file if not needed
                if os.path.exists(file_path):
                    os.remove(file_path)
        else:
            flash('Invalid file type. Only .csv and .xlsx are allowed.', 'danger')
            return redirect(request.url)
    return render_template('admin/warehouse_admin/batch_create_storage.html')


@admin_interface.route('/warehouse_admin/preview_batch_storage', methods=['GET'])
@admin_required('warehouse_admin')
def preview_batch_storage(admin_id):
    """Display preview of uploaded storage data."""
    data = session.get('batch_data')
    if not data:
        flash('No data to preview. Please upload a file first.', 'danger')
        return redirect(url_for('admin_interface.batch_create_storage'))
    return render_template('admin/warehouse_admin/preview_batch_storage.html', data=data)





@admin_interface.route('/warehouse_admin/process_batch_storage', methods=['POST'])
@admin_required('warehouse_admin')
def process_batch_storage(admin_id):
    """Process the batch creation of storage locations."""
    data = session.get('batch_data')
    if not data:
        flash('No data to process. Please upload a file first.', 'danger')
        return redirect(url_for('admin_interface.batch_create_storage'))
    
    errors = []
    for row in data:
        try:
            # Extract and convert all fields from the row
            warehouse_id = int(row['warehouse_id'])
            aisle_number = int(row['aisle_number'])
            shelf_number = int(row['shelf_number'])
            position_number = int(row['position_number'])
            size = int(row['size'])
            location_name = row['location_name']
            
            # Validate warehouse existence
            warehouse = Warehouse.query.get(warehouse_id)
            if not warehouse:
                errors.append(f"Warehouse ID {warehouse_id} not found for location {location_name}")
                continue
            
            # Check for duplicate location
            if WarehouseStorage.query.get(location_name):
                errors.append(f"Storage location '{location_name}' already exists")
                continue
            
            # Create new storage with all required fields
            new_storage = WarehouseStorage(
                location_name=location_name,
                aisle_number=aisle_number,
                shelf_number=shelf_number,
                position_number=position_number,
                size=size,
                warehouse_id=warehouse_id,
                is_available=True
            )
            db.session.add(new_storage)
        except KeyError as e:
            errors.append(f"Missing column {str(e)} in row: {row}")
        except ValueError as e:
            errors.append(f"Invalid data format in row {row}: {str(e)}")
        except Exception as e:
            errors.append(f"Error processing row {row}: {str(e)}")
    
    if errors:
        db.session.rollback()
        session.pop('batch_data', None)
        return render_template('admin/warehouse_admin/batch_storage_result.html', errors=errors)
    else:
        db.session.commit()
        session.pop('batch_data', None)
        flash('All storage locations created successfully!', 'success')
        return redirect(url_for('admin_interface.warehouse_storage'))




# search storage with location and size.
# for available (empty) storage
# for unavailable (with production round), view the corresponding production round
@admin_interface.route('/warehouse_admin/storage/search', methods=['GET'])
@admin_required('warehouse_admin')
def search_warehouse_storage(admin_id):
    """Search for storage locations and display results."""
    # Fetch all warehouses for the dropdown
    warehouses = Warehouse.query.order_by(Warehouse.name).all()

    # Get query parameters
    location_name = request.args.get('location_name', '').strip()
    size = request.args.get('size', '')
    warehouse_id = request.args.get('warehouse_id', '')
    is_available = request.args.get('is_available', '')  # New parameter

    # Start building the query
    storages = WarehouseStorage.query
    if location_name:
        storages = storages.filter(WarehouseStorage.location_name.ilike(f"%{location_name}%"))
    if size:
        storages = storages.filter(WarehouseStorage.size == int(size))
    if warehouse_id:
        storages = storages.filter(WarehouseStorage.warehouse_id == int(warehouse_id))
    if is_available != '':  # Check if a specific value is selected (not "All")
        storages = storages.filter(WarehouseStorage.is_available == (is_available == 'true'))

    storages = storages.order_by(WarehouseStorage.location_name).all()
    return render_template('admin/warehouse_admin/search_warehouse_storage.html', storages=storages, warehouses=warehouses)



# delete storage with is_available=True


@admin_interface.route('/warehouse_admin/storage/delete/<string:storage_name>', methods=['POST'])
@admin_required('warehouse_admin')
def delete_warehouse_storage(admin_id, storage_name):
    """Delete a storage location if it is available."""

    # Fetch the storage by location_name
    storage = WarehouseStorage.query.get(storage_name)
    if not storage:
        flash("Storage location not found.", "danger")
        return redirect(url_for('admin_interface.search_warehouse_storage'))

    if not storage.is_available:
        flash("Cannot delete storage location because it is currently in use.", "danger")
        return redirect(url_for('admin_interface.search_warehouse_storage'))

    try:
        db.session.delete(storage)
        db.session.commit()
        flash("Storage location deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred: {e}", "danger")

    return redirect(url_for('admin_interface.search_warehouse_storage'))


# view record with is_available=False

@admin_interface.route('/warehouse_admin/storage/view_record/<string:storage_location>', methods=['GET'])
@admin_required('warehouse_admin')
def view_warehouse_record(admin_id, storage_location):
    """View the WarehouseRecord associated with an unavailable storage location."""

    # Fetch the storage by location_name
    storage = WarehouseStorage.query.filter_by(location_name=storage_location).first()
    if not storage or storage.is_available:
        flash("No associated record found for this storage location.", "danger")
        return redirect(url_for('admin_interface.search_warehouse_storage'))

    # Fetch associated warehouse record
    warehouse_record = WarehouseRecord.query.filter_by(warehouse_storage_location=storage_location).first()
    if not warehouse_record:
        flash("No record found for this storage location.", "info")
        return redirect(url_for('admin_interface.search_warehouse_storage'))

    # Fetch related product, production round, and artwork
    production_round = warehouse_record.production_round
    product = production_round.product
    artwork = product.artwork  

    # Load production goals as JSON
    stage_goals = []
    if production_round and production_round.production_goals:
        try:
            stage_goals = json.loads(production_round.production_goals)
        except ValueError:
            flash("Error loading stage goals. Please contact support.")

    return render_template(
        'admin/warehouse_admin/view_warehouse_record.html',
        storage=storage,
        warehouse_record=warehouse_record,
        production_round=production_round,
        product=product,
        artwork=artwork,
        stage_goals=stage_goals
    )



@admin_interface.route('/assign_warehouse_to_production_round/<uuid6:production_round_id>', methods=['POST'])
@admin_required('warehouse_admin')
def assign_warehouse_to_production_round(admin_id, production_round_id):
    """
    Assigns a warehouse to all ItemOrderItem records of a given ProductionRound.
    - If `is_accepted` is False:
      1. Updates all items' warehouse records.
      2. Changes `item_status` to "in_stock" if it was "item".
      3. Sets `is_accepted = True` for the production round.
    - If `is_accepted` is True:
      1. Only updates `warehouse_id` for items where `item_status` is "in_stock".
    """

    try:
        # Fetch production round
        production_round = ProductionRound.query.get(production_round_id)
        if not production_round:
            flash("Production Round not found.", "error")
            return redirect(url_for('admin_interface.warehouse_admin_dashboard'))

        # Fetch warehouse mappings
        region_warehouse_map = {m.region_id: m.warehouse_id for m in WarehouseRegionMapping.query.all()}
        if not region_warehouse_map:
            flash("No warehouse-region mappings available.", "error")
            return redirect(url_for('admin_interface.warehouse_admin_dashboard'))

        # Process based on acceptance status
        if not production_round.is_accepted:
            
            items = ItemOrderItem.query.filter_by(production_round_id=production_round_id).all()
            if not items:
                flash("No items found for this Production Round.", "error")
                return redirect(url_for('admin_interface.warehouse_admin_dashboard'))

            for item in items:
                if item.region_id not in region_warehouse_map:
                    flash(f"No warehouse found for region {item.region_id}.", "error")
                    return redirect(url_for('admin_interface.warehouse_admin_dashboard'))
                item.warehouse_id = region_warehouse_map[item.region_id]
                if item.item_status == "item":
                    item.item_status = "in_stock"
                    logging.debug(f"Updated ItemOrderItem {item.id}: status to 'in_stock', warehouse_id={item.warehouse_id}")
                db.session.add(item)
            
            production_round.is_accepted = True
            db.session.add(production_round)

            Notification.send_notification(
                    user_id=production_round.admin_id,
                    message= f"The production round of {production_round.product.name} has been accepted in the warehouse, Update stage to stocking.",
                    type="warehouse_message"
                )
            logging.debug(f"Marked ProductionRound {production_round_id} as accepted")
        else:
            items = ItemOrderItem.query.filter_by(production_round_id=production_round_id, item_status="in_stock").all()
            if not items:
                flash("No 'in_stock' items found to update.", "error")
                return redirect(url_for('admin_interface.warehouse_admin_dashboard'))

            for item in items:
                if item.region_id not in region_warehouse_map:
                    flash(f"No warehouse found for region {item.region_id}.", "error")
                    return redirect(url_for('admin_interface.warehouse_admin_dashboard'))
                item.warehouse_id = region_warehouse_map[item.region_id]
                db.session.add(item)
                logging.debug(f"Updated ItemOrderItem {item.id}: warehouse_id={item.warehouse_id}")

        db.session.commit()
        flash("Warehouse assignment successfully updated.", "success")
        return redirect(url_for('admin_interface.manage_warehouse_record', production_round_id=production_round_id))

    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error assigning warehouse to ProductionRound {production_round_id}: {e}")
        flash(f"Failed to assign warehouse: {str(e)}", "error")
        return redirect(url_for('admin_interface.warehouse_admin_dashboard'))
    




# Warehouse Record management, management and report on how to allocate


@admin_interface.route('/warehouse_admin/record/<uuid6:production_round_id>/create', methods=['POST'])
@admin_required('warehouse_admin')
def create_warehouse_record(admin_id, production_round_id):
    """Create a new warehouse record for a production round."""

    production_round = ProductionRound.query.get(production_round_id)
    if not production_round:
        flash("Production round not found.", "danger")
        return redirect(url_for('admin_interface.warehouse_admin_dashboard'))

    try:
        size = int(request.form.get('size', 0))
        warehouse_id = int(request.form.get('warehouse_id', 0))
        quantity = int(request.form.get('quantity', 0))
        description = request.form.get('description', '')
        warehouse_admin_id = admin_id

        # Validate warehouse_id against assigned warehouses
        assigned_warehouses = (
            db.session.query(ItemOrderItem.warehouse_id)
            .filter(ItemOrderItem.production_round_id == production_round_id)
            .distinct()
            .all()
        )
        assigned_warehouse_ids = {w.warehouse_id for w in assigned_warehouses if w.warehouse_id}
        if warehouse_id not in assigned_warehouse_ids:
            flash(f"Warehouse ID {warehouse_id} is not assigned to this Production Round.", "danger")
            return redirect(url_for('admin_interface.manage_warehouse_record', production_round_id=production_round_id))

        # Fetch warehouse name for error message
        warehouse = Warehouse.query.get(warehouse_id)
        if not warehouse:
            flash(f"Warehouse ID {warehouse_id} not found.", "danger")
            return redirect(url_for('admin_interface.manage_warehouse_record', production_round_id=production_round_id))

        # Select the first available storage location
        storage_location = WarehouseStorage.query.filter_by(
            size=size,
            warehouse_id=warehouse_id,
            is_available=True
        ).first()

        if not storage_location:
            flash(f"No available storage location found for Size {size} in Warehouse {warehouse.name}.", "danger")
            return redirect(url_for('admin_interface.manage_warehouse_record', production_round_id=production_round_id))

        # Create a new warehouse record
        warehouse_record = WarehouseRecord(
            production_round_id=production_round_id,
            warehouse_storage_location=storage_location.location_name,
            quantity=quantity,
            description=description,
            warehouse_admin_id=warehouse_admin_id
        )
        db.session.add(warehouse_record)
        storage_location.is_available = False
        db.session.add(storage_location)

        db.session.flush()
        logging.debug(f"Flushed WarehouseRecord: {warehouse_record.id}, Storage: {storage_location.location_name}")
        db.session.commit()
        logging.debug(f"Committed WarehouseRecord: {warehouse_record.id} for ProductionRound {production_round_id}")
        flash("Warehouse record created successfully!", "success")

    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error creating WarehouseRecord: {e}")
        flash(f"An error occurred: {e}", "danger")

    return redirect(url_for('admin_interface.manage_warehouse_record', production_round_id=production_round_id))



@admin_interface.route('/warehouse_admin/record/<uuid6:production_round_id>', methods=['GET'])
@admin_required('warehouse_admin')
def manage_warehouse_record(admin_id, production_round_id):
    """Display warehouse records for a production round."""

    production_round = ProductionRound.query.get(production_round_id)
    if not production_round:
        flash("Production round not found.", "danger")
        return redirect(url_for('admin_interface.warehouse_admin_dashboard'))
    product = production_round.product
    artwork = product.artwork

    # Fetch existing warehouse records
    warehouse_records = WarehouseRecord.query.filter_by(production_round_id=production_round_id).all()
    logging.debug(f"Fetched {len(warehouse_records)} warehouse records for ProductionRound {production_round_id}")

    return render_template(
        'admin/warehouse_admin/manage_warehouse_record.html',
        artwork=artwork,
        production_round=production_round,
        warehouse_records=warehouse_records
    )







# delete record, free the storage


@admin_interface.route('/warehouse_admin/record/delete/<uuid6:record_id>', methods=['POST'])
@admin_required('warehouse_admin')
def delete_warehouse_record(admin_id, record_id):
    """Delete a specific warehouse record."""

    warehouse_record = WarehouseRecord.query.get(record_id)
    if not warehouse_record:
        flash("Warehouse record not found.")
        return redirect(url_for('admin_interface.warehouse_admin_dashboard'))

    try:
        # Mark the corresponding storage location as available
        storage_location = WarehouseStorage.query.get(warehouse_record.warehouse_storage_location)
        if storage_location:
            storage_location.is_available = True
            db.session.add(storage_location)

        # Delete the warehouse record
        db.session.delete(warehouse_record)
        db.session.commit()
        flash("Warehouse record deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred: {e}", "danger")

    return redirect(url_for('admin_interface.manage_warehouse_record', production_round_id=warehouse_record.production_round_id))




# report on how the item should be allocated among the warehouse (according to self-report region and list)
@admin_interface.route('/warehouse_admin/report_data/<uuid6:production_round_id>', methods=['GET'])
@admin_required('warehouse_admin')
def warehouse_allocation_report_data(admin_id, production_round_id):
    """Fetch warehouse allocation summary for a ProductionRound, only for items with item_status='item'."""

    production_round = ProductionRound.query.get(production_round_id)
    if not production_round:
        return jsonify({"error": "Production round not found"}), 404

    # Fetch warehouse allocation for items with item_status='item'
    warehouse_data = (
        db.session.query(
            Warehouse.id.label("warehouse_id"),
            Warehouse.name.label("warehouse_name"),
            db.func.count(ItemOrderItem.id).label("quantity")
        )
        .join(Warehouse, Warehouse.id == ItemOrderItem.warehouse_id)  # INNER JOIN
        .filter(
            ItemOrderItem.production_round_id == production_round_id,
            ItemOrderItem.item_status == "in_stock"
        )
        .group_by(Warehouse.id, Warehouse.name)
        .all()
    )

    # Log for debugging
    logging.info(f"Warehouse data for ProductionRound {production_round_id}: {warehouse_data}")

    # Format summary
    warehouse_summary = {
        str(warehouse_id): {"name": warehouse_name, "quantity": quantity}
        for warehouse_id, warehouse_name, quantity in warehouse_data
    }
    
    return jsonify(warehouse_summary)




# delivery admin

# delivery dashboard
@admin_interface.route('/delivery_admin/dashboard', methods=['GET', 'POST'])
@admin_required('delivery_admin')
def delivery_admin_dashboard(admin_id):
    """Dashboard for delivery admin to manage delivery orders for their assigned warehouse."""
    delivery_admin = current_user
    warehouse_name = delivery_admin.warehouse.name  # Fetch warehouse name for display

    # Fetch "created" and "paid" delivery orders for the admin's warehouse
    delivery_orders = DeliveryOrder.query.filter(
        DeliveryOrder.warehouse_id == delivery_admin.warehouse_id,
        DeliveryOrder.status == "created",
        DeliveryOrder.payment_status == "paid"
    ).all()

    return render_template(
        'admin/delivery_admin/delivery_admin_dashboard.html',
        delivery_orders=delivery_orders,
        warehouse_name=warehouse_name  # Pass warehouse name for display
    )



@admin_interface.route('/delivery_admin/pick_order/<uuid6:order_id>', methods=['POST'])
@admin_required('delivery_admin')
def pick_delivery_order(admin_id, order_id):
    """Pick a delivery order and set its status to 'in_process'."""
    delivery_order = DeliveryOrder.query.get_or_404(order_id)

    if delivery_order.status == "created":
        delivery_order.status = "in_process"
        db.session.commit()
    
    return redirect(url_for('admin_interface.delivery_admin_dashboard'))




# delivery admin workspace

@admin_interface.route('/delivery_admin/workspace', methods=['GET'])  # Simplified endpoint name
@admin_required('delivery_admin')
def delivery_admin_workspace(admin_id):
    """Workspace for delivery admin to manage in-process delivery orders for their warehouse."""
    delivery_admin = current_user

    # Fetch "in_process" delivery orders for the admin's warehouse
    delivery_orders = DeliveryOrder.query.filter(
        DeliveryOrder.warehouse_id == delivery_admin.warehouse_id,
        DeliveryOrder.status == "in_process"
    ).all()

    if not delivery_orders:
        flash("No in-process orders for this warehouse.", "info")

    # Process grouped items and production rounds
    grouped_items = {}
    production_round_ids = set()
    order_production_rounds = {}

    for order in delivery_orders:
        order_production_rounds[order.id] = []
        for item in order.delivery_item:
            production_round_id = uuid.UUID(item["production_round_id"])
            grouped_items[production_round_id] = grouped_items.get(production_round_id, 0) + item.get("quantity", 1)
            production_round_ids.add(production_round_id)
            order_production_rounds[order.id].append(production_round_id)

    production_round_details = {
        pr.id: {
            "product_name": pr.product.name,
            "artwork_image": pr.product.artwork.image_path,
            "stage_goals": pr.stage_goals
        }
        for pr in ProductionRound.query.filter(ProductionRound.id.in_(production_round_ids)).all()
    }

    # Fetch warehouse records for the admin's warehouse
    warehouse_records = WarehouseRecord.query.filter(
        WarehouseRecord.production_round_id.in_(production_round_ids),
        WarehouseRecord.storage_location.has(WarehouseStorage.warehouse_id == delivery_admin.warehouse_id)
    ).all()

    return render_template(
        'admin/delivery_admin/delivery_admin_workspace.html',
        delivery_orders=delivery_orders,
        grouped_items=grouped_items,
        warehouse_records=warehouse_records,
        production_round_details=production_round_details,
        order_production_rounds=order_production_rounds,
        warehouse_name=delivery_admin.warehouse.name  # Pass warehouse name for display
    )



@admin_interface.route('/delivery_admin/unpick_order/<uuid6:order_id>', methods=['POST'])
@admin_required('delivery_admin')
def unpick_delivery_order(admin_id, order_id):

    delivery_order = DeliveryOrder.query.get_or_404(order_id)
    if delivery_order.status == "in_process":
        delivery_order.status = "created"
        db.session.commit()
    return redirect(url_for('admin_interface.delivery_admin_workspace', warehouse=delivery_order.warehouse_id))





# webpage to assign the package to the delivery order
@admin_interface.route('/delivery_admin/assign_delivery_package_view/<uuid6:order_id>', methods=['GET'])
@admin_required('delivery_admin')
def assign_delivery_package_view(admin_id, order_id):

    # Fetch and validate the DeliveryOrder
    delivery_order = DeliveryOrder.query.get_or_404(order_id)
    if delivery_order.warehouse_id != current_user.warehouse_id:
        flash("This order does not belong to the admin's warehouse.")
        return redirect(url_for('admin_interface.delivery_admin_workspace', warehouse=warehouse))

    # Group items by production round
    grouped_items = {}
    for item_data in delivery_order.delivery_item:
        pr_id = uuid.UUID(item_data["production_round_id"])
        qty = item_data.get("quantity", 1)
        grouped_items[pr_id] = grouped_items.get(pr_id, 0) + qty

    production_round_ids = list(grouped_items.keys())

    # Fetch ProductionRounds for display
    production_rounds = ProductionRound.query.filter(
        ProductionRound.id.in_(production_round_ids)
    ).all()

    production_round_details = {
        pr.id: {
            "product_name": pr.product.name,
            "artwork_image": pr.product.artwork.image_path,
            "stage_goals": pr.stage_goals
        }
        for pr in production_rounds
    }

    # Fetch WarehouseRecords with corrected warehouse filter
    warehouse_records = WarehouseRecord.query.filter(
        WarehouseRecord.production_round_id.in_(production_round_ids),
        WarehouseRecord.storage_location.has(WarehouseStorage.warehouse_id == current_user.warehouse_id)
    ).all()

    return render_template(
        'admin/delivery_admin/assign_delivery_package_view.html',
        delivery_order=delivery_order,
        grouped_items=grouped_items,
        production_round_details=production_round_details,
        warehouse_records=warehouse_records,
        warehouse=current_user.warehouse_id
    )




@admin_interface.route('/delivery_admin/process_assign_delivery_package', methods=['POST'])
@admin_required('delivery_admin')
def process_assign_delivery_package(admin_id):
    """
    A debug route that subtracts the entire needed quantity from *every* selected 
    warehouse record for each ProductionRound. 
    If a record has less than needed, we report insufficient stock.
    """

    print("\n\n===== DEBUG: Entered process_assign_delivery_package route =====")
    try:
        # 1. Extract form data
        order_id_str = request.form.get("order_id")
        warehouse_str = request.form.get("warehouse")
        selected_records_json = request.form.get("selected_warehouse_records_json")
        record_ids = json.loads(selected_records_json)  # List of record UUIDs in string form
        packages_data = request.form.get("packages")

        print(f"DEBUG: order_id_str={order_id_str}")
        print(f"DEBUG: warehouse_str={warehouse_str}")
        print(f"DEBUG: record_ids={record_ids}")
        print(f"DEBUG: packages_data (raw)={packages_data}")

        if not order_id_str or not warehouse_str:
            flash("Missing order or warehouse data.", "danger")
            print("DEBUG: Missing order_id or warehouse. Redirecting to dashboard.")
            return redirect(url_for('admin_interface.delivery_admin_dashboard'))

        order_id = uuid.UUID(order_id_str)
        warehouse_id = int(warehouse_str)

        # Check at least one record & one package
        if not record_ids or not packages_data:
            flash("Please select at least one warehouse record and add at least one package.", "danger")
            print("DEBUG: No records selected or no package data. Redirecting to view.")
            return redirect(url_for('admin_interface.assign_delivery_package_view',
                                    order_id=order_id, warehouse=warehouse_id))

        # Decode JSON packages
        try:
            package_numbers = json.loads(packages_data)
        except json.JSONDecodeError as e:
            flash("Invalid package data format.", "danger")
            print(f"DEBUG: JSONDecodeError => {e}")
            return redirect(url_for('admin_interface.assign_delivery_package_view',
                                    order_id=order_id, warehouse=warehouse_id))

        print(f"DEBUG: package_numbers={package_numbers}")

        # 2. Fetch the DeliveryOrder and validate warehouse
        delivery_order = DeliveryOrder.query.get_or_404(order_id)
        if delivery_order.warehouse_id != warehouse_id:
            flash("Order does not belong to the selected warehouse.", "danger")
            print("DEBUG: Warehouse mismatch.")
            return redirect(url_for('admin_interface.delivery_admin_workspace', warehouse=warehouse_id))
        old_status = delivery_order.status
        print(f"DEBUG: Fetched DeliveryOrder with ID={delivery_order.id}, status={old_status}")

        # 3. Create DeliveryPackage records for each package number
        for pkg_num in package_numbers:
            new_package = DeliveryPackage(
                package_number=pkg_num,
                delivery_order_id=delivery_order.id,
                status="created"
            )
            db.session.add(new_package)
            print(f"DEBUG: Created DeliveryPackage {pkg_num} for order={delivery_order.id}")

        # 4. Build grouped_items to know how much each ProductionRound needs
        grouped_items = {}
        for item_data in delivery_order.delivery_item:
            pr_id = uuid.UUID(item_data["production_round_id"])
            qty = item_data.get("quantity", 1)
            grouped_items[pr_id] = grouped_items.get(pr_id, 0) + qty

        print(f"DEBUG: grouped_items => {grouped_items}")

        # 5. Convert record IDs from string to UUID
        try:
            selected_uuid_list = [uuid.UUID(rid) for rid in record_ids]
        except ValueError as e:
            flash(f"Invalid warehouse record ID encountered: {e}", "danger")
            print(f"DEBUG: Invalid ID => {e}")
            db.session.rollback()
            return redirect(url_for('admin_interface.assign_delivery_package_view',
                                    order_id=order_id, warehouse=warehouse_id))

        # 6. Fetch all chosen records with warehouse filter
        chosen_records = WarehouseRecord.query.filter(
            WarehouseRecord.id.in_(selected_uuid_list),
            WarehouseRecord.storage_location.has(WarehouseStorage.warehouse_id == warehouse_id)
        ).all()

        if len(chosen_records) != len(selected_uuid_list):
            flash("Some selected records are not from this warehouse or do not exist.", "danger")
            print("DEBUG: Record count mismatch after warehouse filter.")
            db.session.rollback()
            return redirect(url_for('admin_interface.assign_delivery_package_view',
                                    order_id=order_id, warehouse=warehouse_id))

        print(f"DEBUG: chosen_records => {[str(r.id) for r in chosen_records]}")

        # 7. For each ProductionRound in the order, subtract its 'needed' from EVERY record
        for pr_id, needed_qty in grouped_items.items():
            print(f"\nDEBUG: Processing PR={pr_id}, needed={needed_qty}")
            
            # Filter chosen_records for this pr_id
            pr_records = [rec for rec in chosen_records if rec.production_round_id == pr_id]

            if not pr_records:
                print(f"DEBUG: No selected warehouse records for PR={pr_id}. Skipping.")
                continue

            # Deduct the entire 'needed_qty' from each record in that PR
            for rec in pr_records:
                print(f"DEBUG: Checking record {rec.id} with qty={rec.quantity}")
                if rec.quantity < needed_qty:
                    db.session.rollback()
                    flash(f"Insufficient stock in record {rec.id} for Production Round {pr_id}. "
                          f"Needed: {needed_qty}, available: {rec.quantity}", "danger")
                    print(f"DEBUG: => record {rec.id} has only {rec.quantity}, can't subtract {needed_qty}. Rolling back.")
                    return redirect(url_for('admin_interface.assign_delivery_package_view',
                                            order_id=order_id, warehouse=warehouse_id))

                old_qty = rec.quantity
                rec.quantity = rec.quantity - needed_qty
                db.session.add(rec)
                print(f"DEBUG: => Deducted {needed_qty} from record {rec.id}, old={old_qty}, new={rec.quantity}")

        # 8. Update the DeliveryOrder status
        delivery_order.status = "delivering"
        db.session.add(delivery_order)
        db.session.commit()

        print(f"DEBUG: Successfully set Order {order_id} status from {old_status} to {delivery_order.status}")
        flash("All selected records for each PR have been fully deducted by the needed amount!", "success")

        # 9. Redirect to workspace
        print("DEBUG: Redirecting to workspace after success.")
        return redirect(url_for('admin_interface.delivery_admin_workspace', warehouse=warehouse_id))

    except Exception as e:
        db.session.rollback()
        flash(f"Error assigning packages: {e}", "danger")
        print(f"DEBUG: Unhandled Exception => {e}")
        return redirect(url_for('admin_interface.delivery_admin_dashboard'))




# Info-admin, manage the warehouse,

@admin_interface.route('/info_admin/dashboard')
@admin_required('info_admin')
def info_admin_dashboard(admin_id):

    return render_template('admin/info_admin/info_admin_dashboard.html')



@admin_interface.route('/info_admin/modification_logs', methods=['GET'])
@admin_required('info_admin')
def view_modification_logs(admin_id):
    logs = ModificationLog.query.order_by(ModificationLog.timestamp.desc()).all()
    return render_template('admin/info_admin/modification_logs.html', logs=logs)





# Regions Management
@admin_interface.route('/info_admin/regions')
@admin_required('info_admin')
def list_regions(admin_id):

    regions = Region.query.all()
    return render_template('admin/info_admin/regions.html', regions=regions)



@admin_interface.route('/info_admin/regions/new', methods=['GET', 'POST'])
@admin_required('info_admin')
def new_region(admin_id):

    if request.method == 'POST':
        name = request.form['name']
        tax_rate = request.form['tax_rate']
        new_region = Region(name=name, tax_rate=tax_rate)
        db.session.add(new_region)
        db.session.commit()

        ModificationLog.log_modification(
            admin_id=admin_id,
            action="add",
            entity_type="region",
            entity_id=new_region.id,
            details=f"Added region: {name} with tax rate {tax_rate}"
        )

        flash("Region added successfully!", "success")
        return redirect(url_for('admin_interface.list_regions'))
    return render_template('admin/info_admin/region_form.html')



@admin_interface.route('/info_admin/regions/edit/<int:id>', methods=['GET', 'POST'])
@admin_required('info_admin')
def edit_region(admin_id, id):

    region = Region.query.get_or_404(id)
    if request.method == 'POST':
        old_name = region.name  # Capture old values for details
        region.name = request.form['name']
        region.tax_rate = request.form['tax_rate']
        db.session.commit()


        ModificationLog.log_modification(
            admin_id=admin_id,
            action="edit",
            entity_type="region",
            entity_id=region.id,  # Fixed: Use id, not name
            details=f"Edited region: {old_name} to name={region.name}, tax_rate={region.tax_rate}"
        )


        flash("Region updated successfully!", "success")
        return redirect(url_for('admin_interface.list_regions'))
    return render_template('admin/info_admin/region_form.html', region=region)



@admin_interface.route('/info_admin/regions/delete/<int:id>', methods=['POST'])
@admin_required('info_admin')
def delete_region(admin_id, id):
    
    region = Region.query.get_or_404(id)
    name = region.name  # Capture name before deletion
    db.session.delete(region)
    db.session.commit()

    ModificationLog.log_modification(
        admin_id=admin_id,
        action="delete",
        entity_type="region",
        entity_id=id,
        details=f"Deleted region: {name}"
    )


    flash("Region deleted successfully!", "success")
    return redirect(url_for('admin_interface.list_regions'))


# Region Batch Import
@admin_interface.route('/info_admin/regions/batch_import', methods=['GET', 'POST'])
@admin_required('info_admin')
def batch_import_regions(admin_id):
    if request.method == 'POST':
        if 'file' not in request.files:
            flash("No file uploaded.", "error")
            return redirect(request.url)

        file = request.files['file']
        if not allowed_file(file.filename):
            flash("Invalid file type. Use .csv or .xlsx.", "error")
            return redirect(request.url)

        try:
            df = process_file(file)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(request.url)
        except Exception as e:
            flash(f"Error reading file: {str(e)}", "error")
            return redirect(request.url)

        required_columns = ['name', 'tax_rate']
        if not all(col in df.columns for col in required_columns):
            flash("Missing required columns: name, tax_rate.", "error")
            return redirect(request.url)

        data = df.to_dict(orient='records')
        session['region_import_preview'] = data
        return render_template('admin/info_admin/batch_import_preview.html', entity_type='region', data=data)

    return render_template('admin/info_admin/batch_import.html', entity_type='region')





@admin_interface.route('/info_admin/regions/batch_import/confirm', methods=['POST'])
@admin_required('info_admin')
def confirm_batch_import_regions(admin_id):
    preview_data = session.get('region_import_preview', [])
    if not preview_data:
        flash("No data to import.", "error")
        return redirect(url_for('admin_interface.list_regions'))

    results = []
    for row in preview_data:
        try:
            if Region.query.filter_by(name=row['name']).first():
                raise ValueError(f"Region {row['name']} already exists.")
            region = Region(
                name=row['name'],
                tax_rate=float(row['tax_rate'])
            )
            db.session.add(region)
            db.session.flush()
            ModificationLog.log_modification(
                admin_id=admin_id,
                action="add",
                entity_type="region",
                entity_id=str(region.id),
                details=f"Batch import: Added region {row['name']} with tax_rate={row['tax_rate']}"
            )
            results.append((True, f"Added region {row['name']}"))
        except Exception as e:
            db.session.rollback()
            results.append((False, f"Error adding {row['name']}: {str(e)}"))
            continue

    db.session.commit()
    session.pop('region_import_preview', None)

    # Check if there are any errors
    errors = [msg for success, msg in results if not success]
    if errors:
        for error in errors:
            flash(error, "error")
    else:
        flash("Batch import completed successfully.", "success")

    return redirect(url_for('admin_interface.list_regions'))




# Warehouse Management
@admin_interface.route('/info_admin/warehouses')
@admin_required('info_admin')
def list_warehouses(admin_id):
    warehouses = Warehouse.query.all()
    return render_template('admin/info_admin/warehouses.html', warehouses=warehouses)



@admin_interface.route('/info_admin/warehouses/new', methods=['GET', 'POST'])
@admin_required('info_admin')
def new_warehouse(admin_id):

    if request.method == 'POST':
        name = request.form['name']
        location = request.form['location']
        new_warehouse = Warehouse(name=name, location=location)
        db.session.add(new_warehouse)
        db.session.commit()


        ModificationLog.log_modification(
            admin_id=admin_id,
            action="add",
            entity_type="warehouse",
            entity_id=new_warehouse.id,
            details=f"Added warehouse: {name} at {location}"
        )


        flash("Warehouse added successfully!", "success")
        return redirect(url_for('admin_interface.list_warehouses'))
    return render_template('admin/info_admin/warehouse_form.html')



@admin_interface.route('/info_admin/warehouses/edit/<int:id>', methods=['GET', 'POST'])
@admin_required('info_admin')
def edit_warehouse(admin_id, id):

    warehouse = Warehouse.query.get_or_404(id)
    if request.method == 'POST':
        old_name = warehouse.name
        warehouse.name = request.form['name']
        warehouse.location = request.form['location']
        db.session.commit()


        ModificationLog.log_modification(
            admin_id=admin_id,
            action="edit",
            entity_type="warehouse",
            entity_id=warehouse.id,
            details=f"Edited warehouse: {old_name} to name={warehouse.name}, location={warehouse.location}"
        )

        flash("Warehouse updated successfully!", "success")
        return redirect(url_for('admin_interface.list_warehouses'))
    return render_template('admin/info_admin/warehouse_form.html', warehouse=warehouse)



@admin_interface.route('/info_admin/warehouses/delete/<int:id>', methods=['POST'])
@admin_required('info_admin')
def delete_warehouse(admin_id, id):

    warehouse = Warehouse.query.get_or_404(id)
    name = warehouse.name
    db.session.delete(warehouse)
    db.session.commit()


    ModificationLog.log_modification(
        admin_id=admin_id,
        action="delete",
        entity_type="warehouse",
        entity_id=id,
        details=f"Deleted warehouse: {name}"
    )


    flash("Warehouse deleted successfully!", "success")
    return redirect(url_for('admin_interface.list_warehouses'))




# Warehouse Batch Import

@admin_interface.route('/info_admin/warehouses/batch_import', methods=['GET', 'POST'])
@admin_required('info_admin')
def batch_import_warehouses(admin_id):
    if request.method == 'POST':
        file = request.files['file']
        if not file or not allowed_file(file.filename):
            flash("Invalid file type. Use .csv or .xlsx.", "error")
            return redirect(request.url)

        df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
        required_columns = ['name', 'location']
        if not all(col in df.columns for col in required_columns):
            flash("Missing required columns: name, location.", "error")
            return redirect(request.url)

        session['warehouse_import_preview'] = df.to_dict(orient='records')
        return render_template('admin/info_admin/batch_import_preview.html', entity_type='warehouse', data=df.to_dict(orient='records'))

    return render_template('admin/info_admin/batch_import.html', entity_type='warehouse')


@admin_interface.route('/info_admin/warehouses/batch_import/confirm', methods=['POST'])
@admin_required('info_admin')
def confirm_batch_import_warehouses(admin_id):
    preview_data = session.get('warehouse_import_preview', [])
    if not preview_data:
        flash("No data to import.", "error")
        return redirect(url_for('admin_interface.list_warehouses'))

    results = []
    for row in preview_data:
        try:
            if Warehouse.query.filter_by(name=row['name']).first():
                raise ValueError(f"Warehouse {row['name']} already exists.")
            warehouse = Warehouse(
                name=row['name'],
                location=row['location']
            )
            db.session.add(warehouse)
            db.session.flush()
            ModificationLog.log_modification(
                admin_id=admin_id,
                action="add",
                entity_type="warehouse",
                entity_id=str(warehouse.id),
                details=f"Batch import: Added warehouse {row['name']} at {row['location']}"
            )
            results.append((True, f"Added warehouse {row['name']}"))
        except Exception as e:
            db.session.rollback()
            results.append((False, f"Error adding {row['name']}: {str(e)}"))
            continue

    db.session.commit()
    session.pop('warehouse_import_preview', None)

    # Check if there are any errors
    errors = [msg for success, msg in results if not success]
    if errors:
        for error in errors:
            flash(error, "error")
    else:
        flash("Batch import completed successfully.", "success")

    return redirect(url_for('admin_interface.list_warehouses'))



# Warehouse-Region Mapping Management
@admin_interface.route('/info_admin/warehouse_mappings')
@admin_required('info_admin')
def list_warehouse_mappings(admin_id):

    mappings = WarehouseRegionMapping.query.all()
    return render_template('admin/info_admin/warehouse_mappings.html', mappings=mappings)

# region-warehoue: many to one, unique relationship
# one region can only have one warehouse
# one warehouse can have many region

@admin_interface.route('/info_admin/warehouse_mappings/new', methods=['GET', 'POST'])
@admin_required('info_admin')
def new_warehouse_mapping(admin_id):

    # Get unmapped regions (i.e., regions NOT already in a mapping)
    mapped_region_ids = [mapping.region_id for mapping in WarehouseRegionMapping.query.all()]
    available_regions = Region.query.filter(Region.id.notin_(mapped_region_ids)).order_by(Region.name).all()

    # Warehouses do NOT have constraints since they can be assigned to multiple regions
    available_warehouses = Warehouse.query.order_by(Warehouse.name).all()

    if request.method == 'POST':
        region_id = request.form.get('region_id')
        warehouse_id = request.form.get('warehouse_id')

        # Ensure valid selection
        if not region_id or not warehouse_id:
            flash("Please select both a region and a warehouse.", "danger")
            return redirect(url_for('admin_interface.new_warehouse_mapping'))

        # Ensure selected region is not already mapped
        if int(region_id) in mapped_region_ids:
            flash("This region is already mapped to a warehouse.", "danger")
            return redirect(url_for('admin_interface.new_warehouse_mapping'))

        # Create new mapping
        new_mapping = WarehouseRegionMapping(region_id=region_id, warehouse_id=warehouse_id)
        db.session.add(new_mapping)
        db.session.commit()

        region = Region.query.get(region_id)
        warehouse = Warehouse.query.get(warehouse_id)

        ModificationLog.log_modification(
            admin_id=admin_id,
            action="add",
            entity_type="warehouse_mapping",
            entity_id=region_id,  # Using region_id as the identifier
            details=f"Added mapping: {region.name} -> {warehouse.name}"
        )

        flash("Mapping added successfully!", "success")
        return redirect(url_for('admin_interface.list_warehouse_mappings'))

    return render_template('admin/info_admin/warehouse_mapping_form.html', available_regions=available_regions, available_warehouses=available_warehouses)


@admin_interface.route('/info_admin/warehouse_mappings/edit/<int:region_id>', methods=['GET', 'POST'])
@admin_required('info_admin')
def edit_warehouse_mapping(admin_id, region_id):
    
    mapping = WarehouseRegionMapping.query.get_or_404(region_id)

    # Get all warehouses since they can have multiple region mappings
    available_warehouses = Warehouse.query.order_by(Warehouse.name).all()

    if request.method == 'POST':
        old_warehouse = Warehouse.query.get(mapping.warehouse_id)
        mapping.warehouse_id = request.form['warehouse_id']
        db.session.commit()

        new_warehouse = Warehouse.query.get(mapping.warehouse_id)
        region = Region.query.get(region_id)
        ModificationLog.log_modification(
            admin_id=admin_id,
            action="edit",
            entity_type="warehouse_mapping",
            entity_id=region_id,
            details=f"Edited mapping: {region.name} from {old_warehouse.name} to {new_warehouse.name}"
        )


        flash("Mapping updated successfully!", "success")
        return redirect(url_for('admin_interface.list_warehouse_mappings'))

    return render_template('admin/info_admin/warehouse_mapping_form.html', mapping=mapping, available_warehouses=available_warehouses)



@admin_interface.route('/info_admin/warehouse_mappings/delete/<int:region_id>', methods=['POST'])
@admin_required('info_admin')
def delete_warehouse_mapping(admin_id, region_id):
    mapping = WarehouseRegionMapping.query.get_or_404(region_id)
    region = Region.query.get(mapping.region_id)
    warehouse = Warehouse.query.get(mapping.warehouse_id)
    db.session.delete(mapping)
    db.session.commit()

    ModificationLog.log_modification(
        admin_id=admin_id,
        action="delete",
        entity_type="warehouse_mapping",
        entity_id=region_id,
        details=f"Deleted mapping: {region.name} -> {warehouse.name}"
    )

    flash("Mapping deleted successfully!", "success")
    return redirect(url_for('admin_interface.list_warehouse_mappings'))


# Warehouse-Region Mapping Batch Import

@admin_interface.route('/info_admin/warehouse_mappings/batch_import', methods=['GET', 'POST'])
@admin_required('info_admin')
def batch_import_warehouse_mappings(admin_id):
    if request.method == 'POST':
        file = request.files['file']
        if not file or not allowed_file(file.filename):
            flash("Invalid file type. Use .csv or .xlsx.", "error")
            return redirect(request.url)

        df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
        required_columns = ['region_name', 'warehouse_name']
        if not all(col in df.columns for col in required_columns):
            flash("Missing required columns: region_name, warehouse_name.", "error")
            return redirect(request.url)

        session['mapping_import_preview'] = df.to_dict(orient='records')
        return render_template('admin/info_admin/batch_import_preview.html', entity_type='warehouse_mapping', data=df.to_dict(orient='records'))

    return render_template('admin/info_admin/batch_import.html', entity_type='warehouse_mapping')



@admin_interface.route('/info_admin/warehouse_mappings/batch_import/confirm', methods=['POST'])
@admin_required('info_admin')
def confirm_batch_import_warehouse_mappings(admin_id):
    preview_data = session.get('mapping_import_preview', [])
    if not preview_data:
        flash("No data to import.", "error")
        return redirect(url_for('admin_interface.list_warehouse_mappings'))

    results = []
    for row in preview_data:
        try:
            region = Region.query.filter_by(name=row['region_name']).first()
            warehouse = Warehouse.query.filter_by(name=row['warehouse_name']).first()
            if not region or not warehouse:
                raise ValueError(f"Region {row['region_name']} or warehouse {row['warehouse_name']} not found.")
            if WarehouseRegionMapping.query.filter_by(region_id=region.id).first():
                raise ValueError(f"Region {row['region_name']} already mapped.")
            mapping = WarehouseRegionMapping(region_id=region.id, warehouse_id=warehouse.id)
            db.session.add(mapping)
            db.session.flush()
            ModificationLog.log_modification(
                admin_id=admin_id,
                action="add",
                entity_type="warehouse_mapping",
                entity_id=str(region.id),
                details=f"Batch import: Added mapping {row['region_name']} -> {row['warehouse_name']}"
            )
            results.append((True, f"Added mapping {row['region_name']} -> {row['warehouse_name']}"))
        except Exception as e:
            db.session.rollback()
            results.append((False, f"Error adding {row['region_name']} -> {row['warehouse_name']}: {str(e)}"))
            continue

    db.session.commit()
    session.pop('mapping_import_preview', None)

    # Check if there are any errors
    errors = [msg for success, msg in results if not success]
    if errors:
        for error in errors:
            flash(error, "error")
    else:
        flash("Batch import completed successfully.", "success")

    return redirect(url_for('admin_interface.list_warehouse_mappings'))


# delivery cost grid management

@admin_interface.route('/info_admin/delivery_cost_grids', methods=['GET'])
@admin_required('info_admin')
def list_delivery_cost_grids(admin_id):

    cost_grids = DeliveryCostGrid.query.all()
    return render_template('admin/info_admin/delivery_cost_grids.html', cost_grids=cost_grids)





@admin_interface.route('/info_admin/delivery_cost_grids/new', methods=['GET', 'POST'])
@admin_required('info_admin')
def new_delivery_cost_grid(admin_id):

    warehouses = Warehouse.query.order_by(Warehouse.name).all()
    regions = Region.query.order_by(Region.name).all()

    if request.method == 'POST':
        warehouse_id = request.form.get('warehouse_id', type=int)
        region_id = request.form.get('region_id', type=int)
        postal_code_prefix = request.form.get('postal_code_prefix', '')
        base_cost = float(request.form.get('base_cost', 0.0))
        per_delivery_point = float(request.form.get('per_delivery_point', 0.0))

        if not warehouse_id or not region_id or base_cost < 0 or per_delivery_point < 0:
            flash("Invalid input. All fields are required and costs must be non-negative.", "error")
            return redirect(url_for('admin_interface.new_delivery_cost_grid'))

        new_grid = DeliveryCostGrid(
            warehouse_id=warehouse_id,
            region_id=region_id,
            postal_code_prefix=postal_code_prefix or None,
            base_cost=base_cost,
            per_delivery_point=per_delivery_point
        )
        db.session.add(new_grid)
        db.session.commit()


        warehouse = Warehouse.query.get(warehouse_id)
        region = Region.query.get(region_id)
        ModificationLog.log_modification(
            admin_id=admin_id,
            action="add",
            entity_type="delivery_cost_grid",
            entity_id=new_grid.id,
            details=f"Added delivery grid: {warehouse.name}/{region.name}, base_cost={base_cost}, per_point={per_delivery_point}"
        )

        flash("Delivery cost grid added successfully!", "success")
        return redirect(url_for('admin_interface.list_delivery_cost_grids'))

    return render_template(
        'admin/info_admin/delivery_cost_grid_form.html',
        warehouses=warehouses,
        regions=regions
    )


@admin_interface.route('/info_admin/delivery_cost_grids/edit/<int:id>', methods=['GET', 'POST'])
@admin_required('info_admin')
def edit_delivery_cost_grid(admin_id, id):

    grid = DeliveryCostGrid.query.get_or_404(id)
    warehouses = Warehouse.query.order_by(Warehouse.name).all()
    regions = Region.query.order_by(Region.name).all()

    if request.method == 'POST':
        old_warehouse = Warehouse.query.get(grid.warehouse_id)
        old_region = Region.query.get(grid.region_id)
        grid.warehouse_id = request.form.get('warehouse_id', type=int)
        grid.region_id = request.form.get('region_id', type=int)
        grid.postal_code_prefix = request.form.get('postal_code_prefix', '') or None
        grid.base_cost = float(request.form.get('base_cost', 0.0))
        grid.per_delivery_point = float(request.form.get('per_delivery_point', 0.0))

        if not grid.warehouse_id or not grid.region_id or grid.base_cost < 0 or grid.per_delivery_point < 0:
            flash("Invalid input. All fields are required and costs must be non-negative.", "error")
            return redirect(url_for('admin_interface.edit_delivery_cost_grid', id=id))

        db.session.commit()

        new_warehouse = Warehouse.query.get(grid.warehouse_id)
        new_region = Region.query.get(grid.region_id)
        ModificationLog.log_modification(
            admin_id=admin_id,
            action="edit",
            entity_type="delivery_cost_grid",
            entity_id=grid.id,
            details=f"Edited delivery grid: {old_warehouse.name}/{old_region.name} to {new_warehouse.name}/{new_region.name}, base_cost={grid.base_cost}, per_point={grid.per_delivery_point}"
        )

        flash("Delivery cost grid updated successfully!", "success")
        return redirect(url_for('admin_interface.list_delivery_cost_grids'))

    return render_template(
        'admin/info_admin/delivery_cost_grid_form.html',
        grid=grid,
        warehouses=warehouses,
        regions=regions
    )


@admin_interface.route('/info_admin/delivery_cost_grids/delete/<int:id>', methods=['POST'])
@admin_required('info_admin')
def delete_delivery_cost_grid(admin_id, id):
    grid = DeliveryCostGrid.query.get_or_404(id)
    warehouse = Warehouse.query.get(grid.warehouse_id)
    region = Region.query.get(grid.region_id)
    db.session.delete(grid)
    db.session.commit()

    ModificationLog.log_modification(
        admin_id=admin_id,
        action="delete",
        entity_type="delivery_cost_grid",
        entity_id=id,
        details=f"Deleted delivery grid: {warehouse.name}/{region.name}"
    )

    flash("Delivery cost grid deleted successfully!", "success")
    return redirect(url_for('admin_interface.list_delivery_cost_grids'))



# Delivery Cost Grid Batch Import

@admin_interface.route('/info_admin/delivery_cost_grids/batch_import', methods=['GET', 'POST'])
@admin_required('info_admin')
def batch_import_delivery_cost_grids(admin_id):
    if request.method == 'POST':
        file = request.files['file']
        if not file or not allowed_file(file.filename):
            flash("Invalid file type. Use .csv or .xlsx.", "error")
            return redirect(request.url)

        df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
        required_columns = ['warehouse_name', 'region_name', 'postal_code_prefix', 'base_cost', 'per_delivery_point']
        if not all(col in df.columns for col in required_columns):
            flash("Missing required columns: warehouse_name, region_name, postal_code_prefix, base_cost, per_delivery_point.", "error")
            return redirect(request.url)

        session['grid_import_preview'] = df.to_dict(orient='records')
        return render_template('admin/info_admin/batch_import_preview.html', entity_type='delivery_cost_grid', data=df.to_dict(orient='records'))

    return render_template('admin/info_admin/batch_import.html', entity_type='delivery_cost_grid')

@admin_interface.route('/info_admin/delivery_cost_grids/batch_import/confirm', methods=['POST'])
@admin_required('info_admin')
def confirm_batch_import_delivery_cost_grids(admin_id):
    preview_data = session.get('grid_import_preview', [])
    if not preview_data:
        flash("No data to import.", "error")
        return redirect(url_for('admin_interface.list_delivery_cost_grids'))

    results = []
    for row in preview_data:
        try:
            warehouse = Warehouse.query.filter_by(name=row['warehouse_name']).first()
            region = Region.query.filter_by(name=row['region_name']).first()
            if not warehouse or not region:
                raise ValueError(f"Warehouse {row['warehouse_name']} or region {row['region_name']} not found.")
            grid = DeliveryCostGrid(
                warehouse_id=warehouse.id,
                region_id=region.id,
                postal_code_prefix=row['postal_code_prefix'] or None,
                base_cost=float(row['base_cost']),
                per_delivery_point=float(row['per_delivery_point'])
            )
            if grid.base_cost < 0 or grid.per_delivery_point < 0:
                raise ValueError("Costs must be non-negative.")
            db.session.add(grid)
            db.session.flush()
            ModificationLog.log_modification(
                admin_id=admin_id,
                action="add",
                entity_type="delivery_cost_grid",
                entity_id=str(grid.id),
                details=f"Batch import: Added grid {row['warehouse_name']}/{row['region_name']}, base_cost={row['base_cost']}, per_point={row['per_delivery_point']}"
            )
            results.append((True, f"Added grid {row['warehouse_name']}/{row['region_name']}"))
        except Exception as e:
            db.session.rollback()
            results.append((False, f"Error adding {row['warehouse_name']}/{row['region_name']}: {str(e)}"))
            continue

    db.session.commit()
    session.pop('grid_import_preview', None)

    # Check if there are any errors
    errors = [msg for success, msg in results if not success]
    if errors:
        for error in errors:
            flash(error, "error")
    else:
        flash("Batch import completed successfully.", "success")

    return redirect(url_for('admin_interface.list_delivery_cost_grids'))



# Modifying the Main Production Species of the ProductionRoundAdmin
@admin_interface.route('/info_admin/search_production_round_admin', methods=['GET', 'POST'])
@admin_required('info_admin')
def search_production_round_admin(admin_id):
    """Search for ProductionRoundAdmin by admin_id, name, or email."""
    search_criteria = {
        "search_admin_id": request.form.get("searchadmin_id", "").strip(),
        "name": request.form.get("name", "").strip(),
        "email": request.form.get("email", "").strip(),
    }

    # Base query
    query = ProductionRoundAdmin.query

    # Fix: Convert admin_id string to UUID for searching
    if search_criteria["search_admin_id"]:
        try:
            admin_uuid = uuid.UUID(search_criteria["search_admin_id"])  # Convert string to UUID
            query = query.filter(ProductionRoundAdmin.id == admin_uuid)
        except ValueError:
            flash("Invalid UUID format for Admin ID.", "danger")

    if search_criteria["name"]:
        query = query.filter(ProductionRoundAdmin.name.ilike(f"%{search_criteria['name']}%"))

    if search_criteria["email"]:
        query = query.filter(ProductionRoundAdmin.email.ilike(f"%{search_criteria['email']}%"))

    production_round_admins = query.all()

    return render_template(
        "admin/info_admin/search_production_round_admin.html",
        production_round_admins=production_round_admins,
        search_criteria=search_criteria
    )


@admin_interface.route('/info_admin/update_production_round_admin', methods=['GET', 'POST'])
@admin_required('info_admin')
def update_production_round_admin(admin_id):
    """Display form and update the main_production_species of a selected ProductionRoundAdmin."""
    
    admin_id_str = request.args.get("admin_id") if request.method == "GET" else request.form.get("selected_admin")

    if not admin_id_str:
        flash("No admin selected for update.", "danger")
        return redirect(url_for('admin_interface.search_production_round_admin'))

    # Convert admin_id from string to UUID
    try:
        admin_uuid = uuid.UUID(admin_id_str)
    except ValueError:
        flash("Invalid Admin ID format.", "danger")
        return redirect(url_for('admin_interface.search_production_round_admin'))

    admin = ProductionRoundAdmin.query.get_or_404(admin_uuid)

    if request.method == "POST":
        old_species = admin.main_production_species
        new_species = request.form.get('main_production_species', '').strip()

        if not new_species:
            flash("Main production species cannot be empty.", "danger")
            return redirect(url_for('admin_interface.update_production_round_admin', admin_id=admin_id_str))

        # ✅ Fix: Ensure the new value is saved
        admin.main_production_species = new_species
        db.session.commit()


        ModificationLog.log_modification(
            admin_id=admin_id,
            action="edit",
            entity_type="production_round_admin",
            entity_id=str(admin.id),
            details=f"Updated ProductionRoundAdmin {admin.name}: main_production_species from {old_species} to {new_species}"
        )

        flash("Main production species updated successfully!", "success")
        return redirect(url_for('admin_interface.search_production_round_admin'))

    return render_template("admin/info_admin/update_production_round_admin.html", admin=admin)




# change the warehouse_id of a delivery order admin


@admin_interface.route('/info_admin/list_delivery_admins')
@admin_required('info_admin')
def list_delivery_admins(admin_id):
    delivery_admins = DeliveryAdmin.query.all()
    return render_template(
        'admin/info_admin/list_delivery_admins.html',
        delivery_admins=delivery_admins,
        admin_id=admin_id  # Pass admin_id to the template
    )
@admin_interface.route('/info_admin/change_delivery_admin_warehouse/<uuid6:admin_id>/<uuid6:delivery_admin_id>', methods=['GET', 'POST'])
@admin_required('info_admin')
def change_delivery_admin_warehouse(admin_id, delivery_admin_id):
    delivery_admin = DeliveryAdmin.query.get_or_404(delivery_admin_id)
    if request.method == 'POST':
        old_warehouse = Warehouse.query.get(delivery_admin.warehouse_id)
        new_warehouse_id = request.form.get('warehouse_id')
        if not new_warehouse_id or not Warehouse.query.get(int(new_warehouse_id)):
            flash("Invalid warehouse selected.", "danger")
            return redirect(url_for('admin_interface.change_delivery_admin_warehouse', admin_id=admin_id, delivery_admin_id=delivery_admin_id))

        delivery_admin.warehouse_id = int(new_warehouse_id)
        db.session.commit()

        new_warehouse = Warehouse.query.get(delivery_admin.warehouse_id)
        ModificationLog.log_modification(
            admin_id=admin_id,
            action="edit",
            entity_type="delivery_admin",
            entity_id=str(delivery_admin.id),
            details=f"Changed warehouse for DeliveryAdmin {delivery_admin.name} from {old_warehouse.name} to {new_warehouse.name}"
        )

        flash(f"Warehouse for {delivery_admin.name} updated successfully!", "success")
        return redirect(url_for('admin_interface.info_admin_dashboard'))

    warehouses = Warehouse.query.all()
    return render_template(
        'admin/info_admin/change_delivery_admin_warehouse.html',
        delivery_admin=delivery_admin,
        warehouses=warehouses
    )

# add admin's function is also here
@admin_interface.route('/info_admin/add_admin', methods=['GET', 'POST'])
@admin_required('info_admin')
def info_admin_add_admin(admin_id):
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']  # New field
        role = request.form['role']
        warehouse_id = request.form.get('warehouse_id')

        # Check if passwords match
        if password != confirm_password:
            flash("Passwords do not match. Please try again.", "danger")
            return redirect(url_for('admin_interface.info_admin_add_admin'))

        existing_admin = db.session.query(Admin).filter_by(email=email).first()
        if existing_admin:
            flash(f"An account with the email {email} already exists.", "danger")
            return redirect(url_for('admin_interface.info_admin_add_admin'))
        
        hashed_password = generate_password_hash(password)
        new_admin = None
        if role == 'artwork_approval_admin':
            new_admin = ArtworkApprovalAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'production_round_admin':
            new_admin = ProductionRoundAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'product_approval_admin':
            new_admin = ProductApprovalAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'warehouse_admin':
            new_admin = WarehouseAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'delivery_admin':
            if not warehouse_id:
                flash("Warehouse ID is required for Delivery Admin.", "danger")
                return redirect(url_for('admin_interface.info_admin_add_admin'))
            new_admin = DeliveryAdmin(name=name, email=email, password_hash=hashed_password, role=role, warehouse_id=int(warehouse_id))
        elif role == 'info_admin':
            new_admin = InfoAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'finance_admin':
            new_admin = FinanceAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'customer_service_admin':
            new_admin = CustomerServiceAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        else:
            flash(f"Invalid role '{role}' specified.", "danger")
            return redirect(url_for('admin_interface.info_admin_add_admin'))

        db.session.add(new_admin)
        db.session.commit()

        ModificationLog.log_modification(
            admin_id=admin_id,
            action="add",
            entity_type="admin",
            entity_id=str(new_admin.id),
            details=f"Added {role} admin: {name} with email {email}"
        )

        flash(f"{role.replace('_', ' ').title()} {name} added successfully!", "success")
        return redirect(url_for('admin_interface.info_admin_add_admin'))

    warehouses = Warehouse.query.all()
    return render_template('admin/info_admin/add_admin.html', warehouses=warehouses)




# New batch import admin route
@admin_interface.route('/info_admin/batch_import_admin', methods=['GET', 'POST'])
@admin_required('info_admin')
def info_admin_batch_import_admin(admin_id):
    if request.method == 'POST':
        # Check if the form is a confirmation submission
        if 'confirm' in request.form:
            # Retrieve the preview data from the session
            admins_data_json = session.get('admins_data_preview')
            if not admins_data_json:
                flash('No preview data available. Please upload a file first.', 'danger')
                return redirect(request.url)
            
            admins_data = pd.read_json(admins_data_json, orient='records')
            success_count = 0
            errors = []
            
            for admin_data in admins_data.to_dict('records'):
                name = admin_data.get('name')
                email = admin_data.get('email')
                password = admin_data.get('password')
                role = admin_data.get('role')
                warehouse_id = admin_data.get('warehouse_id')

                # Validate required fields
                if not all([name, email, password, role]):
                    errors.append(f"Missing required field for admin with email {email or 'unknown'}")
                    continue

                # Validate role
                valid_roles = [
                    'artwork_approval_admin', 'production_round_admin', 'product_approval_admin',
                    'warehouse_admin', 'delivery_admin', 'info_admin', 'finance_admin', 'customer_service_admin'
                ]
                if role not in valid_roles:
                    errors.append(f"Invalid role '{role}' for admin with email {email}")
                    continue

                # Special handling for delivery_admin
                if role == 'delivery_admin':
                    if not warehouse_id:
                        errors.append(f"Warehouse ID is required for delivery admin with email {email}")
                        continue
                    try:
                        warehouse_id = int(warehouse_id)
                        warehouse = Warehouse.query.get(warehouse_id)
                        if not warehouse:
                            errors.append(f"Invalid warehouse ID {warehouse_id} for delivery admin with email {email}")
                            continue
                    except ValueError:
                        errors.append(f"Invalid warehouse ID '{warehouse_id}' for delivery admin with email {email}")
                        continue

                # Check for existing email
                existing_admin = db.session.query(Admin).filter_by(email=email).first()
                if existing_admin:
                    errors.append(f"An account with the email {email} already exists.")
                    continue

                # Hash password and create new admin
                hashed_password = generate_password_hash(password)
                new_admin = None
                if role == 'artwork_approval_admin':
                    new_admin = ArtworkApprovalAdmin(name=name, email=email, password_hash=hashed_password, role=role)
                elif role == 'production_round_admin':
                    new_admin = ProductionRoundAdmin(name=name, email=email, password_hash=hashed_password, role=role)
                elif role == 'product_approval_admin':
                    new_admin = ProductApprovalAdmin(name=name, email=email, password_hash=hashed_password, role=role)
                elif role == 'warehouse_admin':
                    new_admin = WarehouseAdmin(name=name, email=email, password_hash=hashed_password, role=role)
                elif role == 'delivery_admin':
                    new_admin = DeliveryAdmin(name=name, email=email, password_hash=hashed_password, role=role, warehouse_id=warehouse_id)
                elif role == 'info_admin':
                    new_admin = InfoAdmin(name=name, email=email, password_hash=hashed_password, role=role)
                elif role == 'finance_admin':
                    new_admin = FinanceAdmin(name=name, email=email, password_hash=hashed_password, role=role)
                elif role == 'customer_service_admin':
                    new_admin = CustomerServiceAdmin(name=name, email=email, password_hash=hashed_password, role=role)

                db.session.add(new_admin)
                success_count += 1
                ModificationLog.log_modification(
                    admin_id=admin_id,
                    action="add",
                    entity_type="admin",
                    entity_id=str(new_admin.id),
                    details=f"Added {role} admin: {name} with email {email}"
                )

            db.session.commit()
            session.pop('admins_data_preview', None)  # Clear the session data

            if success_count > 0:
                flash(f"Successfully added {success_count} admins.", "success")
            if errors:
                for error in errors:
                    flash(error, "danger")
            return redirect(request.url)

        # Handle file upload and preview
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            try:
                # Process the file directly into a DataFrame
                admins_data = process_file(file)
                # Convert required columns to strings to prevent type issues
                for col in ['name', 'email', 'password', 'role']:
                    if col in admins_data.columns:
                        admins_data[col] = admins_data[col].astype(str)
                # Convert DataFrame to JSON and store in session for preview
                session['admins_data_preview'] = admins_data.to_json(orient='records')
                return render_template(
                    'admin/info_admin/batch_import_admin.html',
                    preview_data=admins_data.to_dict('records'),
                    columns=admins_data.columns.tolist()
                )
            except Exception as e:
                flash(f"Error processing file: {str(e)}", "danger")
                return redirect(request.url)
        else:
            flash('Invalid file type. Only CSV and XLSX are allowed.', 'danger')
            return redirect(request.url)

    return render_template('admin/info_admin/batch_import_admin.html')








@admin_interface.route('/info_admin/list_admins_for_password')
@admin_required('info_admin')
def list_admins_for_password(admin_id):
    admins = Admin.query.all()
    return render_template(
        'admin/info_admin/list_admins_for_password.html',
        admins=admins,
        admin_id=admin_id  # Pass admin_id to the template
    )

    


@admin_interface.route('/info_admin/change_admin_password/<uuid6:admin_id>/<uuid6:change_admin_id>', methods=['GET', 'POST'])
@admin_required('info_admin')
def change_admin_password(admin_id, change_admin_id):
    change_admin = Admin.query.get_or_404(change_admin_id)
    if request.method == 'POST':
        new_password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not new_password or new_password != confirm_password:
            flash("Passwords do not match or are empty.", "danger")
            return redirect(url_for('admin_interface.change_admin_password', admin_id=admin_id, change_admin_id=change_admin_id))

        change_admin.password_hash = generate_password_hash(new_password)
        db.session.commit()

        ModificationLog.log_modification(
            admin_id=admin_id,
            action="edit",
            entity_type="admin",
            entity_id=str(change_admin.id),
            details=f"Changed password for admin: {change_admin.name}"
        )

        flash(f"Password for {change_admin.name} updated successfully!", "success")
        return redirect(url_for('admin_interface.info_admin_dashboard'))

    return render_template(
        'admin/info_admin/change_admin_password.html',
        change_admin=change_admin
    )



# finance admin, approve/reject AccountingTransaction


@admin_interface.route('/finance_admin_dashboard', methods=['GET'])
@admin_required('finance_admin')
def finance_admin_dashboard(admin_id):
    # Fetch unassigned transactions
    unassigned_transactions = AccountingTransaction.query.filter_by(finance_admin_id=None).all()
    
    # Group by transaction_type
    grouped_transactions = {}
    for transaction in unassigned_transactions:
        grouped_transactions.setdefault(transaction.transaction_type, []).append(transaction)
    
    return render_template(
        'admin/finance_admin/dashboard.html',
        grouped_transactions=grouped_transactions
    )



@admin_interface.route('/assign_transaction/<uuid6:transaction_id>', methods=['POST'])
@admin_required('finance_admin')
def assign_transaction(admin_id, transaction_id):
    transaction = AccountingTransaction.query.get(transaction_id)
    if transaction and transaction.finance_admin_id is None:
        transaction.finance_admin_id = admin_id
        db.session.commit()
        flash("Transaction assigned successfully.")
    else:
        flash("Transaction not found or already assigned.")
    return redirect(request.referrer or url_for('admin_interface.finance_admin_dashboard'))


# picked AccountingTransaction appears in workspace to be approved/rejected

@admin_interface.route('/finance_admin_workspace', methods=['GET'])
@admin_required('finance_admin')
def finance_admin_workspace(admin_id):
    assigned_transactions = AccountingTransaction.query.filter_by(
        finance_admin_id=admin_id,
        status='requested'
    ).all()

    unread_notifications_count = Notification.get_unread_notifications_count(admin_id)

    return render_template(
        'admin/finance_admin/workspace.html',
        transactions=assigned_transactions,
        unread_notifications_count=unread_notifications_count
    )


@admin_interface.route('/approve_transaction/<uuid6:transaction_id>', methods=['POST'])
@admin_required('finance_admin')
def approve_transaction(admin_id, transaction_id):
    transaction = AccountingTransaction.query.get(transaction_id)
    if transaction and transaction.finance_admin_id == admin_id and transaction.status == 'requested':
        transaction.status = 'approved'
        transaction.approved_at = datetime.now()
        # Handle artist_payout-specific logic if Payout and Artist models exist
        if transaction.transaction_type == 'artist_payout':
            payout = Payout.query.filter_by(accounting_transaction_id=transaction.id).first()
            if payout:
                payout.status = 'completed'
                artist = Artist.query.get(payout.artist_id)
                if artist:
                    artist.wallet_balance += payout.total_amount
        db.session.commit()
        # Send notification to production round admin
        if transaction.production_round and transaction.production_round.admin_id:
            message = f"The {transaction.transaction_type} transaction of {transaction.production_round.product.name} has been approved."
            Notification.send_notification(transaction.production_round.admin_id, message, 'transaction')
        flash("Transaction approved successfully.")
    else:
        flash("Transaction not found, not assigned to you, or already processed.")
    return redirect(url_for('admin_interface.finance_admin_workspace'))

@admin_interface.route('/reject_transaction/<uuid6:transaction_id>', methods=['POST'])
@admin_required('finance_admin')
def reject_transaction(admin_id, transaction_id):
    transaction = AccountingTransaction.query.get(transaction_id)
    if transaction and transaction.finance_admin_id == admin_id and transaction.status == 'requested':
        transaction.status = 'rejected'
        db.session.commit()
        # Send notification to production round admin
        if transaction.production_round and transaction.production_round.admin_id:
            message = f"! Rejected! The {transaction.transaction_type} transaction of {transaction.production_round.product.name} has been rejected."
            Notification.send_notification(transaction.production_round.admin_id, message, 'transaction')
        flash("Transaction rejected successfully.")
    else:
        flash("Transaction not found, not assigned to you, or already processed.")
    return redirect(url_for('admin_interface.finance_admin_workspace'))




@admin_interface.route('/finance_admin_historical_records', methods=['GET'])
@admin_required('finance_admin')
def finance_admin_historical_records(admin_id):
    historical_transactions = AccountingTransaction.query.filter(
        AccountingTransaction.finance_admin_id == admin_id,
        AccountingTransaction.status.in_(['approved', 'rejected'])
    ).all()
    return render_template(
        'admin/finance_admin/historical_records.html',
        transactions=historical_transactions
    )


@admin_interface.route('/search_transactions', methods=['GET', 'POST'])
@admin_required('finance_admin')
def search_transactions(admin_id):
    if request.method == 'POST':
        # Collect search criteria
        filters = []
        
        # ID
        id_str = request.form.get('id', '').strip()
        if id_str:
            try:
                filters.append(AccountingTransaction.id == uuid.UUID(id_str))
            except ValueError:
                flash("Invalid ID format. Please enter a valid UUID.")

        # Transaction Type (enhanced with ilike)
        transaction_type = request.form.get('transaction_type', '').strip()
        if transaction_type and transaction_type != 'any':
            filters.append(AccountingTransaction.transaction_type.ilike(f'%{transaction_type}%'))

        # Amount Range
        amount_min = request.form.get('amount_min', '').strip()
        amount_max = request.form.get('amount_max', '').strip()
        if amount_min:
            try:
                filters.append(AccountingTransaction.amount >= float(amount_min))
            except ValueError:
                flash("Invalid minimum amount.")
        if amount_max:
            try:
                filters.append(AccountingTransaction.amount <= float(amount_max))
            except ValueError:
                flash("Invalid maximum amount.")

        # Status
        status = request.form.get('status', '').strip()
        if status and status != 'any':
            filters.append(AccountingTransaction.status == status)

        # Created At Range
        created_at_start = request.form.get('created_at_start', '').strip()
        created_at_end = request.form.get('created_at_end', '').strip()
        if created_at_start:
            try:
                filters.append(AccountingTransaction.created_at >= datetime.strptime(created_at_start, '%Y-%m-%d'))
            except ValueError:
                flash("Invalid created_at start date (use YYYY-MM-DD).")
        if created_at_end:
            try:
                filters.append(AccountingTransaction.created_at <= datetime.strptime(created_at_end, '%Y-%m-%d'))
            except ValueError:
                flash("Invalid created_at end date (use YYYY-MM-DD).")

        # Approved At Range
        approved_at_start = request.form.get('approved_at_start', '').strip()
        approved_at_end = request.form.get('approved_at_end', '').strip()
        if approved_at_start:
            try:
                filters.append(AccountingTransaction.approved_at >= datetime.strptime(approved_at_start, '%Y-%m-%d'))
            except ValueError:
                flash("Invalid approved_at start date (use YYYY-MM-DD).")
        if approved_at_end:
            try:
                filters.append(AccountingTransaction.approved_at <= datetime.strptime(approved_at_end, '%Y-%m-%d'))
            except ValueError:
                flash("Invalid approved_at end date (use YYYY-MM-DD).")

        # Finance Admin ID
        finance_admin_id = request.form.get('finance_admin_id', '').strip()
        if finance_admin_id:
            try:
                filters.append(AccountingTransaction.finance_admin_id == uuid.UUID(finance_admin_id))
            except ValueError:
                flash("Invalid Finance Admin ID format. Please enter a valid UUID.")

        # Production Round ID
        production_round_id = request.form.get('production_round_id', '').strip()
        if production_round_id:
            try:
                filters.append(AccountingTransaction.production_round_id == uuid.UUID(production_round_id))
            except ValueError:
                flash("Invalid Production Round ID format. Please enter a valid UUID.")

        # Query with filters
        transactions = AccountingTransaction.query.filter(and_(*filters)).all()
        return render_template(
            'admin/finance_admin/search_results.html',
            transactions=transactions,
            search_params=request.form,
            admin_id=admin_id
        )

    # GET: Render the search form
    return render_template('admin/finance_admin/search_transactions.html')



@admin_interface.route('/request_stop_processing/<uuid6:transaction_id>', methods=['POST'])
@admin_required('finance_admin')
def request_stop_processing(admin_id, transaction_id):
    transaction = AccountingTransaction.query.get(transaction_id)
    if transaction and transaction.finance_admin_id and transaction.status == 'requested':
        Notification.send_notification(
            user_id=transaction.finance_admin_id,
            message=f"Please stop processing transaction {transaction.id}.",
            type="stop_processing_request"
        )
        flash("Notification sent to the assigned admin.")
    else:
        flash("Transaction not found, not assigned, or not in 'requested' status.")
    return redirect(request.referrer or url_for('admin_interface.finance_admin_dashboard'))




# View notifications for the logged-in user, unread ones in first page, the read ones are displayed in a separate page
# these are for the admins, which might need to be adjusted...? or just the webpage?
# hmm... but the notification page definitely need to be duplicated for the users (customers and artists) and admins...?
# maybe not, since the notifications are the same for all users, just the roles are different?

@admin_interface.route('/view_notifications', methods=['GET', 'POST'])
@admin_role_required
def view_notifications():

    user_id = current_user.id
    unread_notifications = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.timestamp.desc()).all()

    # Categorize notifications
    categorized_notifications = {}
    for notification in unread_notifications:
        if notification.type not in categorized_notifications:
            categorized_notifications[notification.type] = []
        categorized_notifications[notification.type].append(notification)

    # Mark notifications as read if requested
    if request.method == 'POST':
        for notification in unread_notifications:
            notification.is_read = True
        db.session.commit()
        flash("All notifications marked as read.")

    return render_template('admin/account/unread_notifications.html', categorized_notifications=categorized_notifications)


@admin_interface.route('/mark_notification_read/<uuid6:notification_id>', methods=['POST'])
@admin_role_required
def mark_notification_read(notification_id):

    try:
        # Find the notification by ID
        notification = Notification.query.get(notification_id)

        # Ensure the notification belongs to the logged-in user

        if notification.user_id != current_user.id:
            flash("You are not authorized to mark this notification as read.")
            return redirect(url_for('admin_interface.view_notifications'))

        # Mark the notification as read
        notification.is_read = True
        db.session.commit()
        flash("Notification has been marked as read.")

    except Exception as e:
        flash("An error occurred while trying to mark the notification as read.")

    return redirect(url_for('admin_interface.view_notifications'))




@admin_interface.route('/view_read_notifications', methods=['GET', 'POST'])
@admin_role_required
def view_read_notifications():
    
    # Calculate the date 6 months ago
    six_months_ago = datetime.now(timezone.utc) - relativedelta(months=6)

    # Delete read notifications older than 6 months
    Notification.query.filter(
        Notification.user_id == current_user.id,
        Notification.is_read == True,
        Notification.timestamp < six_months_ago
    ).delete()
    db.session.commit()

    # Query remaining read notifications
    read_notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=True
    ).order_by(Notification.timestamp.desc()).all()

    # Categorize notifications
    categorized_notifications = {}
    for notification in read_notifications:
        if notification.type not in categorized_notifications:
            categorized_notifications[notification.type] = []
        categorized_notifications[notification.type].append(notification)

    has_read_notifications = bool(read_notifications)

    return render_template(
        'admin/account/read_notifications.html',
        categorized_notifications=categorized_notifications,
        has_read_notifications=has_read_notifications
    )


@admin_interface.route('/delete_all_read_notifications', methods=['POST'])
@admin_role_required
def delete_all_read_notifications():

   
    # Delete all read notifications for the user
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=True
    ).delete()
    db.session.commit()

    flash("All read notifications have been deleted.")
    return redirect(url_for('admin_interface.view_read_notifications'))


@admin_interface.route('/product_dialog/<uuid6:product_id>', methods=['GET', 'POST'])
@admin_required('production_round_admin')
def admin_active_product_dialog(admin_id, product_id):


    # Fetch the active production round
    production_round = ProductionRound.query.filter_by(product_id=product_id, is_active=True).first()
    if not production_round:
        flash("No active production round found for this product.")
        return redirect(url_for('admin_interface.admin_dashboard'))

    # Check if the admin is authorized
    if production_round.admin_id != admin_id:
        flash("Unauthorized access to this dialog.")
        return redirect(url_for('admin_interface.admin_dashboard'))

    if request.method == 'POST':
        message = request.form.get('message')
        uploaded_files = request.files.getlist('files')

        # Create and save a new message
        new_message = Dialog(
            production_round_id=production_round.id,
            sender_id=admin_id,
            message=message or '[File Attached]',
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add(new_message)
        db.session.commit()

        # Handle file uploads
        upload_folder = current_app.config['UPLOAD_FOLDER']
        for file in uploaded_files:
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file_path = os.path.join(upload_folder, filename)

                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)

                file.save(file_path)

                new_file = DialogFile(
                    dialog_id=new_message.id,
                    file_path=f'uploads/{filename}',
                    file_name=filename,
                    upload_date=datetime.now(timezone.utc)
                )
                db.session.add(new_file)

        db.session.commit()
        flash("Message and files sent.")

        # Notify the artist
        recipient_id = production_round.artist_id
        Notification.send_notification(
            user_id=recipient_id,
            message=f"You have a new message in the production round for '{production_round.product.name}'.",
            type='dialog'
        )

    # Fetch all messages in this dialog
    messages = Dialog.query.filter_by(production_round_id=production_round.id).order_by(Dialog.timestamp).all()

    return render_template('admin/production_round_admin/product_dialog.html', production_round=production_round, messages=messages)
