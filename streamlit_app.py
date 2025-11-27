import streamlit as st
import re
import csv
import io
from pathlib import Path
from html import unescape
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart

# Page configuration
st.set_page_config(
    page_title="Instructor Evaluation Parser",
    page_icon="📊",
    layout="wide"
)

def extract_survey_items(text):
    """Extract survey item descriptions from the text."""
    items = {}
    # Look for "Instructor Survey Items:" followed by numbered items
    items_section = re.search(r'Instructor Survey Items:\s*\n((?:\d+\.\s+[^\n]+\n?)+)', text)
    if items_section:
        items_text = items_section.group(1)
        # Extract each numbered item
        item_pattern = r'(\d+)\.\s+(.+?)(?:\n|$)'
        for match in re.finditer(item_pattern, items_text):
            item_num = int(match.group(1))
            item_text = match.group(2).strip()
            items[item_num] = item_text
    return items

def create_short_name(full_text):
    """Create a shorter, CSV-friendly name from the full survey item text."""
    # Map known survey items to shorter names
    item_mapping = {
        "The instructor explained concepts clearly.": "Explained clearly",
        "The instructor used effective teaching methods.": "Effective teaching methods",
        "The instructor interacted with students in a respectful, professional manner.": "Respectful interaction",
        "The instructor was knowledgeable in the subject area.": "Knowledgeable",
        "Overall, I rate the instructor highly.": "Overall rating"
    }
    
    # Check if we have a direct mapping
    if full_text in item_mapping:
        return item_mapping[full_text]
    
    # Fallback: remove "The instructor" prefix and capitalize
    short = full_text.replace('The instructor ', '').replace('the instructor ', '')
    # Remove trailing period
    short = short.rstrip('.')
    # Capitalize first letter
    if short:
        short = short[0].upper() + short[1:] if len(short) > 1 else short.upper()
    return short

def create_abbreviated_header(short_name):
    """Create an abbreviated header name for table columns."""
    # Map to very short abbreviations for table headers
    abbreviation_mapping = {
        "Explained clearly": "Explained",
        "Effective teaching methods": "Teaching",
        "Respectful interaction": "Respectful",
        "Knowledgeable": "Knowledge",
        "Overall rating": "Overall"
    }
    
    # Check if we have a direct mapping
    if short_name in abbreviation_mapping:
        return abbreviation_mapping[short_name]
    
    # Fallback: use first word or first few letters
    words = short_name.split()
    if len(words) > 0:
        return words[0][:8]  # First 8 characters of first word
    return short_name[:8]

def get_academic_year(semester, year):
    """Determine academic year from semester and year.
    Academic year runs Fall through Summer (e.g., Fall 2022-Summer 2023 = 2022-2023).
    """
    if not semester or not year:
        return None
    
    semester = semester.strip()
    year = int(year) if isinstance(year, (int, str)) and str(year).isdigit() else None
    
    if not year:
        return None
    
    # Fall semester starts the academic year
    if semester == 'Fall':
        return f"{year}-{year + 1}"
    # Winter, Spring, Summer belong to the academic year that started the previous Fall
    elif semester in ['Winter', 'Spring', 'Summer']:
        return f"{year - 1}-{year}"
    else:
        return None

def organize_by_term(data_list):
    """Organize evaluation data by term within each academic year.
    Returns a dictionary: {academic_year: {term: [courses]}}
    Term order: Fall, Winter, Spring, Summer
    """
    term_order = {'Fall': 1, 'Winter': 2, 'Spring': 3, 'Summer': 4}
    organized = {}
    
    for data in data_list:
        semester = data.get('Semester', '')
        year = data.get('Year', '')
        academic_year = get_academic_year(semester, year)
        
        if not academic_year:
            continue
        
        if academic_year not in organized:
            organized[academic_year] = {}
        
        if semester not in organized[academic_year]:
            organized[academic_year][semester] = []
        
        organized[academic_year][semester].append(data)
    
    # Sort terms within each academic year
    for academic_year in organized:
        sorted_terms = sorted(organized[academic_year].items(), 
                             key=lambda x: term_order.get(x[0], 99))
        organized[academic_year] = dict(sorted_terms)
    
    return organized

def parse_evaluation_content(content, filename=""):
    """Parse evaluation file content and extract all data."""
    # Extract content from <pre> tag
    pre_match = re.search(r'<pre[^>]*>(.*?)</pre>', content, re.DOTALL)
    if not pre_match:
        return None
    
    text = pre_match.group(1)
    text = unescape(text)  # Handle HTML entities like &amp;
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Initialize result dictionary
    result = {}
    result['_filename'] = filename
    
    # Extract semester and year
    semester_match = re.search(r'(Winter|Spring|Summer|Fall)\s+(\d{4})', text)
    if semester_match:
        result['Semester'] = semester_match.group(1)
        result['Year'] = int(semester_match.group(2))
    else:
        result['Semester'] = ''
        result['Year'] = ''
    
    # Extract enrollment
    enrollment_match = re.search(r'enrollment for course at start of quarter:\s*N\s*=\s*(\d+)', text, re.IGNORECASE)
    if enrollment_match:
        result['Enrollment'] = int(enrollment_match.group(1))
    else:
        result['Enrollment'] = ''
    
    # Extract course code and name
    course_code_match = re.search(r'^([A-Z]+\s+\d+[A-Z]?)\s*:\s*', text, re.MULTILINE)
    if course_code_match:
        result['Course_Code'] = course_code_match.group(1).strip()
        # Find the start position after the colon
        start_pos = course_code_match.end()
        # Find the next line that looks like an instructor name (LASTNAME, FIRSTNAME)
        instructor_line_match = re.search(r'\n([A-Z]+,\s+[A-Z\s]+)\s*$', text[start_pos:], re.MULTILINE)
        if instructor_line_match:
            # Extract everything between the colon and the instructor name
            course_name_text = text[start_pos:start_pos + instructor_line_match.start()].strip()
            # Clean up course name - remove extra whitespace and newlines
            course_name = re.sub(r'\s+', ' ', course_name_text)
            result['Course_Name'] = course_name
        else:
            # Fallback: just get the rest of the line
            line_end = text.find('\n', start_pos)
            if line_end == -1:
                line_end = len(text)
            course_name = re.sub(r'\s+', ' ', text[start_pos:line_end].strip())
            result['Course_Name'] = course_name
    else:
        result['Course_Code'] = ''
        result['Course_Name'] = ''
    
    # Extract instructor name
    instructor_match = re.search(r'^([A-Z]+,\s+[A-Z\s]+)$', text, re.MULTILINE)
    if instructor_match:
        result['Instructor'] = instructor_match.group(1).strip()
    else:
        result['Instructor'] = ''
    
    # Parse item statistics
    item_pattern = r'^\s*(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)%'
    
    items = []
    for line in lines:
        match = re.match(item_pattern, line)
        if match:
            item_num = int(match.group(1))
            items.append({
                'item': item_num,
                'rank': int(match.group(2)),
                'mean': float(match.group(3)),
                'sd': float(match.group(4)),
                'n': int(match.group(5)),
                'pct_strongly_agree': int(match.group(6)),
                'pct_agree': int(match.group(7)),
                'pct_neutral': int(match.group(8)),
                'pct_disagree': int(match.group(9)),
                'pct_strongly_disagree': int(match.group(10)),
                'response_rate': int(match.group(11))
            })
    
    # Sort items by item number
    items.sort(key=lambda x: x['item'])
    
    # Extract survey items for column naming
    survey_items = extract_survey_items(text)
    
    # Add item data to result
    for item in items:
        item_num = item['item']
        result[f'Item_{item_num}_Rank'] = item['rank']
        result[f'Item_{item_num}_Mean'] = item['mean']
        result[f'Item_{item_num}_SD'] = item['sd']
        result[f'Item_{item_num}_N'] = item['n']
        result[f'Item_{item_num}_Pct_Strongly_Agree'] = item['pct_strongly_agree']
        result[f'Item_{item_num}_Pct_Agree'] = item['pct_agree']
        result[f'Item_{item_num}_Pct_Neutral'] = item['pct_neutral']
        result[f'Item_{item_num}_Pct_Disagree'] = item['pct_disagree']
        result[f'Item_{item_num}_Pct_Strongly_Disagree'] = item['pct_strongly_disagree']
        result[f'Item_{item_num}_Response_Rate'] = item['response_rate']
    
    # Store survey items in result
    result['_survey_items'] = survey_items
    
    # Parse overall statistics
    overall_pattern = r'Over\s*All\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)%'
    overall_match = re.search(overall_pattern, text, re.MULTILINE)
    if overall_match:
        result['Overall_Mean'] = float(overall_match.group(1))
        result['Overall_SD'] = float(overall_match.group(2))
        result['Overall_N'] = int(overall_match.group(3))
        result['Overall_Pct_Strongly_Agree'] = int(overall_match.group(4))
        result['Overall_Pct_Agree'] = int(overall_match.group(5))
        result['Overall_Pct_Neutral'] = int(overall_match.group(6))
        result['Overall_Pct_Disagree'] = int(overall_match.group(7))
        result['Overall_Pct_Strongly_Disagree'] = int(overall_match.group(8))
    else:
        result['Overall_Mean'] = ''
        result['Overall_SD'] = ''
        result['Overall_N'] = ''
        result['Overall_Pct_Strongly_Agree'] = ''
        result['Overall_Pct_Agree'] = ''
        result['Overall_Pct_Neutral'] = ''
        result['Overall_Pct_Disagree'] = ''
        result['Overall_Pct_Strongly_Disagree'] = ''
    
    return result

def process_files(uploaded_files):
    """Process uploaded files and return data with annual PDFs grouped by academic year."""
    all_data = []
    annual_pdf_data_list = []  # List of tuples: (pdf_bytes, filename, course_count)
    survey_items = None
    processed_count = 0
    error_count = 0
    
    for uploaded_file in uploaded_files:
        try:
            content = uploaded_file.read().decode('utf-8')
            data = parse_evaluation_content(content, uploaded_file.name)
            if data:
                # Extract survey items from first file
                if survey_items is None and '_survey_items' in data:
                    survey_items = data['_survey_items']
                
                # Remove internal keys before adding to all_data
                data_copy = data.copy()
                if '_survey_items' in data_copy:
                    del data_copy['_survey_items']
                if '_filename' in data_copy:
                    del data_copy['_filename']
                all_data.append(data_copy)
                processed_count += 1
            else:
                error_count += 1
        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {str(e)}")
            error_count += 1
    
    # Use default survey items if none found
    if survey_items is None or len(survey_items) == 0:
        survey_items = {
            1: "The instructor explained concepts clearly.",
            2: "The instructor used effective teaching methods.",
            3: "The instructor interacted with students in a respectful, professional manner.",
            4: "The instructor was knowledgeable in the subject area.",
            5: "Overall, I rate the instructor highly."
        }
    
    # Group data by instructor and academic year, then generate annual PDFs
    if all_data:
        # Group by instructor first
        by_instructor = {}
        for data in all_data:
            instructor = data.get('Instructor', 'UNKNOWN')
            if instructor not in by_instructor:
                by_instructor[instructor] = []
            by_instructor[instructor].append(data)
        
        # For each instructor, group by academic year and generate PDFs
        for instructor, instructor_data in by_instructor.items():
            # Organize by academic year and term
            organized = organize_by_term(instructor_data)
            
            # Generate PDF for each academic year
            for academic_year, year_data in organized.items():
                try:
                    pdf_bytes = generate_annual_pdf_report(year_data, instructor, academic_year, survey_items)
                    pdf_filename = generate_annual_pdf_filename(instructor, academic_year)
                    # Count total courses in this academic year
                    total_courses = sum(len(courses) for courses in year_data.values())
                    annual_pdf_data_list.append((pdf_bytes, pdf_filename, total_courses))
                except Exception as pdf_error:
                    st.warning(f"Could not generate PDF for {instructor} - {academic_year}: {str(pdf_error)}")
    
    return all_data, survey_items, processed_count, error_count, annual_pdf_data_list

def create_dataframe(all_data, survey_items):
    """Create a pandas DataFrame with descriptive column names."""
    if not all_data:
        return pd.DataFrame()
    
    # Sort by Year and Semester
    semester_order = {'Winter': 1, 'Spring': 2, 'Summer': 3, 'Fall': 4}
    all_data.sort(key=lambda x: (x.get('Year', 0), semester_order.get(x.get('Semester', ''), 99)))
    
    # Map data to descriptive column names
    mapped_data = []
    for row in all_data:
        mapped_row = {
            'Semester': row.get('Semester', ''),
            'Year': row.get('Year', ''),
            'Course_Code': row.get('Course_Code', ''),
            'Course_Name': row.get('Course_Name', ''),
            'Instructor': row.get('Instructor', ''),
            'Enrollment': row.get('Enrollment', '')
        }
        
        # Map item data
        for item_num in range(1, 6):
            if item_num in survey_items:
                item_name = create_short_name(survey_items[item_num])
            else:
                item_name = f'Item {item_num}'
            
            mapped_row[f'{item_name} - Rank'] = row.get(f'Item_{item_num}_Rank', '')
            mapped_row[f'{item_name} - Mean'] = row.get(f'Item_{item_num}_Mean', '')
            mapped_row[f'{item_name} - SD'] = row.get(f'Item_{item_num}_SD', '')
            mapped_row[f'{item_name} - N'] = row.get(f'Item_{item_num}_N', '')
            mapped_row[f'{item_name} - % Strongly Agree'] = row.get(f'Item_{item_num}_Pct_Strongly_Agree', '')
            mapped_row[f'{item_name} - % Agree'] = row.get(f'Item_{item_num}_Pct_Agree', '')
            mapped_row[f'{item_name} - % Neutral'] = row.get(f'Item_{item_num}_Pct_Neutral', '')
            mapped_row[f'{item_name} - % Disagree'] = row.get(f'Item_{item_num}_Pct_Disagree', '')
            mapped_row[f'{item_name} - % Strongly Disagree'] = row.get(f'Item_{item_num}_Pct_Strongly_Disagree', '')
            mapped_row[f'{item_name} - Response Rate'] = row.get(f'Item_{item_num}_Response_Rate', '')
        
        # Map overall data
        mapped_row['Overall - Mean'] = row.get('Overall_Mean', '')
        mapped_row['Overall - SD'] = row.get('Overall_SD', '')
        mapped_row['Overall - N'] = row.get('Overall_N', '')
        mapped_row['Overall - % Strongly Agree'] = row.get('Overall_Pct_Strongly_Agree', '')
        mapped_row['Overall - % Agree'] = row.get('Overall_Pct_Agree', '')
        mapped_row['Overall - % Neutral'] = row.get('Overall_Pct_Neutral', '')
        mapped_row['Overall - % Disagree'] = row.get('Overall_Pct_Disagree', '')
        mapped_row['Overall - % Strongly Disagree'] = row.get('Overall_Pct_Strongly_Disagree', '')
        
        mapped_data.append(mapped_row)
    
    return pd.DataFrame(mapped_data)

def generate_csv(df):
    """Generate CSV string from DataFrame."""
    output = io.StringIO()
    df.to_csv(output, index=False)
    return output.getvalue()

def generate_annual_pdf_filename(instructor_name, academic_year):
    """Generate filename for annual PDF report."""
    instructor_lastname = instructor_name.split(',')[0].strip() if instructor_name else 'UNKNOWN'
    instructor_lastname = re.sub(r'[^\w\-_]', '', instructor_lastname)
    return f"{instructor_lastname}_{academic_year}.pdf"

def create_term_chart(term_data, survey_items, term_name):
    """Create a bar chart showing average ratings for each survey item across all courses in a term."""
    # Calculate average for each item across all courses
    item_means = {}
    for item_num in range(1, 6):
        values = []
        for course in term_data:
            mean = course.get(f'Item_{item_num}_Mean', '')
            if mean != '' and mean is not None and isinstance(mean, (int, float)):
                values.append(mean)
        if values:
            item_means[item_num] = sum(values) / len(values)
        else:
            item_means[item_num] = 0
    
    # Get item names
    item_names = []
    for item_num in range(1, 6):
        if item_num in survey_items:
            item_name = create_short_name(survey_items[item_num])
            # Truncate long names
            if len(item_name) > 20:
                item_name = item_name[:17] + '...'
            item_names.append(item_name)
        else:
            item_names.append(f'Item {item_num}')
    
    # Create the chart
    fig, ax = plt.subplots(figsize=(6, 3.5))
    bars = ax.bar(range(len(item_names)), [item_means[i] for i in range(1, 6)], 
                   color=['#2c5aa0', '#3d6bb3', '#5a7fb8', '#7a9bc4', '#9ab5d0'])
    
    # Add value labels on bars
    for i, (bar, value) in enumerate(zip(bars, [item_means[i] for i in range(1, 6)])):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.05,
                f'{value:.2f}',
                ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax.set_xticks(range(len(item_names)))
    ax.set_xticklabels(item_names, rotation=15, ha='right', fontsize=9)
    ax.set_ylabel('Average Rating', fontsize=10, fontweight='bold')
    ax.set_title(f'{term_name} - Average Ratings by Survey Item', fontsize=11, fontweight='bold', pad=10)
    ax.set_ylim(0, 5.5)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.axhline(y=4.0, color='green', linestyle='--', alpha=0.5, linewidth=1, label='Target (4.0)')
    
    plt.tight_layout()
    
    # Save to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    return buf

def create_overall_trend_chart(year_data, academic_year):
    """Create a line chart showing overall rating trends across terms."""
    term_order = ['Fall', 'Winter', 'Spring', 'Summer']
    terms = []
    overall_means = []
    
    for term in term_order:
        if term in year_data and year_data[term]:
            term_courses = year_data[term]
            values = []
            for course in term_courses:
                overall = course.get('Overall_Mean', '')
                if overall != '' and overall is not None and isinstance(overall, (int, float)):
                    values.append(overall)
            if values:
                terms.append(term)
                overall_means.append(sum(values) / len(values))
    
    if len(terms) < 2:
        return None  # Need at least 2 points for a trend
    
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot(terms, overall_means, marker='o', linewidth=2.5, markersize=8, 
            color='#2c5aa0', markerfacecolor='#5a7fb8', markeredgewidth=2, markeredgecolor='#1f4788')
    
    # Add value labels
    for term, value in zip(terms, overall_means):
        ax.text(term, value + 0.1, f'{value:.2f}', ha='center', va='bottom', 
                fontsize=9, fontweight='bold')
    
    ax.set_ylabel('Average Overall Rating', fontsize=10, fontweight='bold')
    ax.set_title(f'Academic Year {academic_year} - Overall Rating Trend', 
                 fontsize=11, fontweight='bold', pad=10)
    ax.set_ylim(0, 5.5)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.axhline(y=4.0, color='green', linestyle='--', alpha=0.5, linewidth=1)
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    return buf

def create_term_summary_table(term_data, survey_items):
    """Create a summary table for all courses in a term.
    Returns table data ready for ReportLab Table.
    """
    # Build header row with abbreviated names
    header = ['Course', 'Enroll']
    
    # Add item mean columns with abbreviated names
    for item_num in range(1, 6):
        if item_num in survey_items:
            item_name = create_short_name(survey_items[item_num])
            abbrev = create_abbreviated_header(item_name)
        else:
            abbrev = f'Item{item_num}'
        header.append(abbrev)
    
    header.append('Overall')
    header.append('Resp %')
    
    # Build data rows
    rows = [header]
    
    for course in term_data:
        row = []
        # Combine Course Code and Name, truncate name to save space
        course_code = course.get('Course_Code', 'N/A')
        course_name = course.get('Course_Name', 'N/A')
        # Limit course name to 25 characters
        if len(course_name) > 25:
            course_name = course_name[:22] + '...'
        # Combine: "CODE: Name"
        combined = f"{course_code}: {course_name}" if course_name != 'N/A' else course_code
        row.append(combined)
        
        # Enrollment
        row.append(str(course.get('Enrollment', 'N/A')) if course.get('Enrollment', '') != '' else 'N/A')
        
        # Add item means
        for item_num in range(1, 6):
            mean = course.get(f'Item_{item_num}_Mean', '')
            if mean != '' and mean is not None and isinstance(mean, (int, float)):
                row.append(f"{mean:.2f}")
            else:
                row.append('N/A')
        
        # Overall mean
        overall_mean = course.get('Overall_Mean', '')
        if overall_mean != '' and overall_mean is not None and isinstance(overall_mean, (int, float)):
            row.append(f"{overall_mean:.2f}")
        else:
            row.append('N/A')
        
        # Response rate (use first item's response rate as representative)
        response_rate = course.get('Item_1_Response_Rate', '')
        if response_rate != '' and response_rate is not None:
            row.append(f"{response_rate}%")
        else:
            row.append('N/A')
        
        rows.append(row)
    
    return rows

def generate_annual_pdf_report(year_data, instructor_name, academic_year, survey_items):
    """Generate a professional annual PDF report for an academic year, organized by term.
    year_data: dict with structure {term: [list of course data]}
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                           rightMargin=0.5*inch, leftMargin=0.5*inch,
                           topMargin=0.75*inch, bottomMargin=0.75*inch)
    
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1f4788'),
        spaceAfter=15,
        alignment=TA_CENTER,
        leading=28
    )
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.HexColor('#5a7fb8'),
        spaceAfter=25,
        alignment=TA_CENTER,
        leading=18
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2c5aa0'),
        spaceAfter=10,
        spaceBefore=25
    )
    term_style = ParagraphStyle(
        'TermHeading',
        parent=styles['Heading2'],
        fontSize=15,
        textColor=colors.HexColor('#1f4788'),
        spaceAfter=10,
        spaceBefore=20,
        borderWidth=0,
        borderPadding=5,
        backColor=colors.HexColor('#e8eef5')
    )
    summary_style = ParagraphStyle(
        'Summary',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#666666'),
        spaceAfter=8,
        alignment=TA_LEFT
    )
    
    # Title Section with enhanced styling
    title_text = f"<b>Instructor Evaluation Report</b>"
    elements.append(Paragraph(title_text, title_style))
    
    subtitle_text = f"{instructor_name}<br/>Academic Year {academic_year}"
    elements.append(Paragraph(subtitle_text, subtitle_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Add overall trend chart at the beginning if we have multiple terms
    trend_chart = create_overall_trend_chart(year_data, academic_year)
    if trend_chart:
        try:
            img = Image(trend_chart, width=6*inch, height=3*inch)
            elements.append(img)
            elements.append(Spacer(1, 0.25*inch))
        except:
            pass  # Skip chart if there's an error
    
    # Process each term in order: Fall, Winter, Spring, Summer
    term_order = ['Fall', 'Winter', 'Spring', 'Summer']
    
    for term in term_order:
        if term not in year_data or not year_data[term]:
            continue
        
        term_courses = year_data[term]
        
        # Term header with background
        term_year = term_courses[0].get('Year', '') if term_courses else ''
        term_header = f"{term} {term_year}"
        elements.append(Paragraph(term_header, term_style))
        elements.append(Spacer(1, 0.15*inch))
        
        # Add term summary statistics
        total_enrollment = sum(c.get('Enrollment', 0) or 0 for c in term_courses if isinstance(c.get('Enrollment'), (int, float)))
        avg_overall = []
        for course in term_courses:
            overall = course.get('Overall_Mean', '')
            if overall != '' and overall is not None and isinstance(overall, (int, float)):
                avg_overall.append(overall)
        avg_overall_str = f"{sum(avg_overall)/len(avg_overall):.2f}" if avg_overall else "N/A"
        
        summary_text = f"<b>Summary:</b> {len(term_courses)} course(s) | Total Enrollment: {total_enrollment} | Average Overall Rating: {avg_overall_str}"
        elements.append(Paragraph(summary_text, summary_style))
        elements.append(Spacer(1, 0.1*inch))
        
        # Add term chart
        try:
            term_chart_buf = create_term_chart(term_courses, survey_items, f"{term} {term_year}")
            chart_img = Image(term_chart_buf, width=5.5*inch, height=3.2*inch)
            elements.append(chart_img)
            elements.append(Spacer(1, 0.15*inch))
        except Exception as e:
            pass  # Skip chart if there's an error
        
        # Create summary table for this term with enhanced styling
        table_data = create_term_summary_table(term_courses, survey_items)
        
        if table_data and len(table_data) > 1:
            # Convert header row to Paragraph objects with rotation for slanted text
            header_style = ParagraphStyle(
                'TableHeader',
                parent=styles['Normal'],
                fontSize=9,
                textColor=colors.whitesmoke,
                fontName='Helvetica-Bold',
                alignment=TA_CENTER,
                leading=10
            )
            
            # Replace header strings with Paragraph objects (rotated text)
            header_row = table_data[0]
            rotated_headers = []
            for header_text in header_row:
                # Use Paragraph for text wrapping, with slight rotation effect via smaller font
                # ReportLab doesn't support true rotation in tables, so we'll use wrapped text
                para = Paragraph(f"<b>{header_text}</b>", header_style)
                rotated_headers.append(para)
            
            # Replace first row with Paragraph objects
            table_data[0] = rotated_headers
            
            # Calculate column widths - adjusted for combined Course column
            num_cols = len(table_data[0])
            available_width = 7*inch
            # New structure: Course (combined), Enroll, 5 items, Overall, Resp %
            if num_cols == 9:  # Course, Enroll, 5 items, Overall, Resp %
                col_widths = [2.2*inch, 0.5*inch] + [0.55*inch] * 5 + [0.6*inch, 0.5*inch]
            else:
                # Fallback: flexible distribution
                col_widths = [2.0*inch] + [0.55*inch] * (num_cols - 1)
            
            total_width = sum(col_widths)
            if total_width > available_width:
                scale = available_width / total_width
                col_widths = [w * scale for w in col_widths]
            
            term_table = Table(table_data, colWidths=col_widths, repeatRows=1)
            
            # Enhanced table styling
            term_table.setStyle(TableStyle([
                # Header row - enhanced with more padding for rotated text
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('TOPPADDING', (0, 0), (-1, 0), 12),
                ('LEFTPADDING', (0, 0), (-1, 0), 4),
                ('RIGHTPADDING', (0, 0), (-1, 0), 4),
                ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#0d3d6b')),
                # Data rows - enhanced readability
                ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # Course (combined)
                ('ALIGN', (1, 1), (1, -1), 'CENTER'),  # Enrollment
                ('ALIGN', (2, 1), (-1, -1), 'CENTER'),  # All numeric columns
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (0, -1), 8.5),  # Course column slightly smaller
                ('FONTSIZE', (1, 1), (-1, -1), 9),  # Other columns
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('LEFTPADDING', (0, 1), (-1, -1), 4),
                ('RIGHTPADDING', (0, 1), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d0d0d0')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f7fa')]),
                ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
                # Add color coding for high ratings (4.0+)
                ('TEXTCOLOR', (2, 1), (6, -1), colors.HexColor('#2d5a27')),  # Green for item means
                ('TEXTCOLOR', (7, 1), (7, -1), colors.HexColor('#1f4788')),  # Blue for overall
                # Left border for first column
                ('LINEBEFORE', (0, 0), (0, -1), 1, colors.HexColor('#e0e0e0')),
            ]))
            elements.append(term_table)
            elements.append(Spacer(1, 0.3*inch))
    
    # Add page break before detailed course breakdowns
    elements.append(PageBreak())
    
    # Detailed Course-by-Course Breakdown Section
    section_heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1f4788'),
        spaceAfter=15,
        spaceBefore=10,
        alignment=TA_CENTER
    )
    
    elements.append(Paragraph("<b>Detailed Course-by-Course Breakdown</b>", section_heading_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Process each term again for detailed breakdowns
    for term in term_order:
        if term not in year_data or not year_data[term]:
            continue
        
        term_courses = year_data[term]
        term_year = term_courses[0].get('Year', '') if term_courses else ''
        
        # Term section header
        elements.append(Paragraph(f"<b>{term} {term_year}</b>", heading_style))
        elements.append(Spacer(1, 0.15*inch))
        
        # Detailed breakdown for each course in this term
        for course_idx, course in enumerate(term_courses, 1):
            course_code = course.get('Course_Code', 'N/A')
            course_name = course.get('Course_Name', 'N/A')
            instructor = course.get('Instructor', 'N/A')
            enrollment = course.get('Enrollment', 'N/A')
            semester = course.get('Semester', 'N/A')
            year = course.get('Year', 'N/A')
            
            # Course header
            course_header_style = ParagraphStyle(
                'CourseHeader',
                parent=styles['Heading2'],
                fontSize=12,
                textColor=colors.HexColor('#2c5aa0'),
                spaceAfter=8,
                spaceBefore=12
            )
            
            course_title = f"<b>{course_code}: {course_name}</b>"
            elements.append(Paragraph(course_title, course_header_style))
            
            # Course info table
            info_data = [
                ['Instructor:', instructor],
                ['Semester:', f"{semester} {year}"],
                ['Enrollment:', str(enrollment) if enrollment != 'N/A' else 'N/A']
            ]
            
            info_table = Table(info_data, colWidths=[1.5*inch, 5.5*inch])
            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8eef5')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(info_table)
            elements.append(Spacer(1, 0.1*inch))
            
            # Survey Items Statistics
            items_data = [['Survey Item', 'Mean', 'SD', 'N', 'Rank', 'Response Rate']]
            
            for item_num in range(1, 6):
                if item_num in survey_items:
                    item_text = survey_items[item_num]
                    # Truncate long item text
                    if len(item_text) > 50:
                        item_text = item_text[:47] + '...'
                else:
                    item_text = f"Item {item_num}"
                
                mean = course.get(f'Item_{item_num}_Mean', '')
                sd = course.get(f'Item_{item_num}_SD', '')
                n = course.get(f'Item_{item_num}_N', '')
                rank = course.get(f'Item_{item_num}_Rank', '')
                response_rate = course.get(f'Item_{item_num}_Response_Rate', '')
                
                mean_str = f"{mean:.2f}" if mean != '' and mean is not None and isinstance(mean, (int, float)) else 'N/A'
                sd_str = f"{sd:.2f}" if sd != '' and sd is not None and isinstance(sd, (int, float)) else 'N/A'
                n_str = str(n) if n != '' and n is not None else 'N/A'
                rank_str = str(rank) if rank != '' and rank is not None else 'N/A'
                resp_str = f"{response_rate}%" if response_rate != '' and response_rate is not None else 'N/A'
                
                items_data.append([item_text, mean_str, sd_str, n_str, rank_str, resp_str])
            
            # Overall statistics
            overall_mean = course.get('Overall_Mean', '')
            overall_sd = course.get('Overall_SD', '')
            overall_n = course.get('Overall_N', '')
            
            overall_mean_str = f"{overall_mean:.2f}" if overall_mean != '' and overall_mean is not None and isinstance(overall_mean, (int, float)) else 'N/A'
            overall_sd_str = f"{overall_sd:.2f}" if overall_sd != '' and overall_sd is not None and isinstance(overall_sd, (int, float)) else 'N/A'
            overall_n_str = str(overall_n) if overall_n != '' and overall_n is not None else 'N/A'
            
            items_data.append(['<b>Overall</b>', overall_mean_str, overall_sd_str, overall_n_str, '—', '—'])
            
            items_table = Table(items_data, colWidths=[3.5*inch, 0.7*inch, 0.7*inch, 0.6*inch, 0.6*inch, 0.8*inch])
            items_table.setStyle(TableStyle([
                # Header
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                # Data rows
                ('ALIGN', (0, 1), (0, -1), 'LEFT'),
                ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ('TOPPADDING', (0, 1), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f7fa')]),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                # Overall row styling
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8eef5')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ]))
            elements.append(items_table)
            
            # Response distribution table
            dist_header = ['Response', 'Strongly Agree', 'Agree', 'Neutral', 'Disagree', 'Strongly Disagree']
            dist_data = [dist_header]
            
            for item_num in range(1, 6):
                if item_num in survey_items:
                    item_text = survey_items[item_num]
                    if len(item_text) > 30:
                        item_text = item_text[:27] + '...'
                else:
                    item_text = f"Item {item_num}"
                
                pct_sa = course.get(f'Item_{item_num}_Pct_Strongly_Agree', '')
                pct_a = course.get(f'Item_{item_num}_Pct_Agree', '')
                pct_n = course.get(f'Item_{item_num}_Pct_Neutral', '')
                pct_d = course.get(f'Item_{item_num}_Pct_Disagree', '')
                pct_sd = course.get(f'Item_{item_num}_Pct_Strongly_Disagree', '')
                
                dist_data.append([
                    item_text,
                    f"{pct_sa}%" if pct_sa != '' and pct_sa is not None else 'N/A',
                    f"{pct_a}%" if pct_a != '' and pct_a is not None else 'N/A',
                    f"{pct_n}%" if pct_n != '' and pct_n is not None else 'N/A',
                    f"{pct_d}%" if pct_d != '' and pct_d is not None else 'N/A',
                    f"{pct_sd}%" if pct_sd != '' and pct_sd is not None else 'N/A'
                ])
            
            # Overall response distribution
            overall_pct_sa = course.get('Overall_Pct_Strongly_Agree', '')
            overall_pct_a = course.get('Overall_Pct_Agree', '')
            overall_pct_n = course.get('Overall_Pct_Neutral', '')
            overall_pct_d = course.get('Overall_Pct_Disagree', '')
            overall_pct_sd = course.get('Overall_Pct_Strongly_Disagree', '')
            
            dist_data.append([
                '<b>Overall</b>',
                f"{overall_pct_sa}%" if overall_pct_sa != '' and overall_pct_sa is not None else 'N/A',
                f"{overall_pct_a}%" if overall_pct_a != '' and overall_pct_a is not None else 'N/A',
                f"{overall_pct_n}%" if overall_pct_n != '' and overall_pct_n is not None else 'N/A',
                f"{overall_pct_d}%" if overall_pct_d != '' and overall_pct_d is not None else 'N/A',
                f"{overall_pct_sd}%" if overall_pct_sd != '' and overall_pct_sd is not None else 'N/A'
            ])
            
            dist_table = Table(dist_data, colWidths=[2.5*inch, 0.9*inch, 0.9*inch, 0.9*inch, 0.9*inch, 0.9*inch])
            dist_table.setStyle(TableStyle([
                # Header
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5a7fb8')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                # Data rows
                ('ALIGN', (0, 1), (0, -1), 'LEFT'),
                ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ('TOPPADDING', (0, 1), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f7fa')]),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                # Overall row
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8eef5')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ]))
            
            elements.append(Spacer(1, 0.1*inch))
            elements.append(dist_table)
            elements.append(Spacer(1, 0.2*inch))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

# Main app
st.title("📊 Instructor Evaluation Parser")
st.markdown("Upload HTML evaluation files to extract and analyze instructor evaluation data.")

# File upload
st.header("Upload Files")
uploaded_files = st.file_uploader(
    "Choose HTML files",
    type=['html', 'htm', 'HTM', 'HTML'],
    accept_multiple_files=True,
    help="Select one or more HTML evaluation files to process"
)

if uploaded_files:
    st.success(f"📁 {len(uploaded_files)} file(s) selected")
    
    # Process button
    if st.button("🚀 Process Files", type="primary"):
        with st.spinner("Processing files..."):
            all_data, survey_items, processed_count, error_count, annual_pdf_data_list = process_files(uploaded_files)
            
            if all_data:
                # Create DataFrame
                df = create_dataframe(all_data, survey_items)
                
                # Store in session state
                st.session_state['df'] = df
                st.session_state['survey_items'] = survey_items
                st.session_state['annual_pdf_data_list'] = annual_pdf_data_list
                
                # Show success message
                st.success(f"✅ Successfully processed {processed_count} file(s)!")
                if error_count > 0:
                    st.warning(f"⚠️ {error_count} file(s) could not be processed.")
                
                # Show summary statistics
                st.header("📈 Summary Statistics")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Evaluations", len(df))
                with col2:
                    if 'Year' in df.columns and not df['Year'].empty:
                        st.metric("Year Range", f"{df['Year'].min()}-{df['Year'].max()}")
                with col3:
                    if 'Overall - Mean' in df.columns:
                        overall_mean = pd.to_numeric(df['Overall - Mean'], errors='coerce').mean()
                        st.metric("Average Overall Rating", f"{overall_mean:.2f}")
                with col4:
                    if 'Enrollment' in df.columns:
                        total_enrollment = pd.to_numeric(df['Enrollment'], errors='coerce').sum()
                        st.metric("Total Enrollment", int(total_enrollment))
                
                # Show data preview
                st.header("📋 Data Preview")
                st.dataframe(df, use_container_width=True, height=400)
                
                # Download Annual PDFs Section
                st.header("📄 Download Annual PDF Reports")
                pdf_count = len(annual_pdf_data_list)
                if pdf_count > 0:
                    st.success(f"✅ {pdf_count} annual PDF report(s) generated successfully!")
                    
                    # Display PDF download buttons with academic year and course count
                    if pdf_count <= 3:
                        # Show all PDFs in columns if 3 or fewer
                        cols = st.columns(min(pdf_count, 3))
                        pdf_idx = 0
                        for pdf_bytes, pdf_filename, course_count in annual_pdf_data_list:
                            if pdf_bytes is not None:
                                with cols[pdf_idx % len(cols)]:
                                    # Extract academic year from filename for display
                                    academic_year = pdf_filename.replace('.pdf', '').split('_')[-1] if '_' in pdf_filename else 'Unknown'
                                    st.download_button(
                                        label=f"📥 {academic_year}\n({course_count} courses)",
                                        data=pdf_bytes,
                                        file_name=pdf_filename,
                                        mime="application/pdf",
                                        key=f"annual_pdf_download_{pdf_idx}",
                                        help=f"Academic Year {academic_year} - {course_count} courses"
                                    )
                                pdf_idx += 1
                    else:
                        # Use expandable sections for many PDFs
                        with st.expander(f"📄 Download Annual PDF Reports ({pdf_count} academic years)", expanded=True):
                            pdf_idx = 0
                            for pdf_bytes, pdf_filename, course_count in annual_pdf_data_list:
                                if pdf_bytes is not None:
                                    # Extract academic year from filename for display
                                    academic_year = pdf_filename.replace('.pdf', '').split('_')[-1] if '_' in pdf_filename else 'Unknown'
                                    col1, col2 = st.columns([3, 1])
                                    with col1:
                                        st.markdown(f"**Academic Year {academic_year}** - {course_count} courses")
                                        st.caption(pdf_filename)
                                    with col2:
                                        st.download_button(
                                            label="📥 Download",
                                            data=pdf_bytes,
                                            file_name=pdf_filename,
                                            mime="application/pdf",
                                            key=f"annual_pdf_download_{pdf_idx}"
                                        )
                                    pdf_idx += 1
                else:
                    st.warning("⚠️ No PDFs could be generated. Please check the file format.")
                
                # Download CSV
                st.header("💾 Download CSV")
                csv_data = generate_csv(df)
                st.download_button(
                    label="📥 Download CSV",
                    data=csv_data,
                    file_name="evaluations.csv",
                    mime="text/csv"
                )

                # Quick visual summaries for at-a-glance performance
                st.header("📊 Quick Visual Summary")
                try:
                    numeric_df = df.copy()
                    # Convert all ' - Mean' columns to numeric
                    mean_cols = [c for c in df.columns if c.endswith(' - Mean')]
                    numeric_df[mean_cols] = numeric_df[mean_cols].apply(pd.to_numeric, errors='coerce')

                    # Bar chart: average of each survey item (exclude Overall)
                    item_mean_cols = [c for c in mean_cols if not c.startswith('Overall')]
                    if item_mean_cols:
                        avg_item_means = numeric_df[item_mean_cols].mean().rename(lambda x: x.replace(' - Mean',''))
                        st.subheader('Average Item Means')
                        st.bar_chart(avg_item_means)

                    # Line chart: Overall mean over time (requires Year and Semester)
                    if 'Overall - Mean' in df.columns:
                        semester_order = {'Winter': 1, 'Spring': 2, 'Summer': 3, 'Fall': 4}
                        df_times = numeric_df.copy()
                        df_times['Year'] = pd.to_numeric(df_times['Year'], errors='coerce')
                        df_times['SemesterOrder'] = df_times['Semester'].map(semester_order).fillna(99)
                        df_times = df_times.sort_values(['Year', 'SemesterOrder'])
                        df_times['Period'] = df_times.apply(
                            lambda r: f"{int(r['Year'])} {r['Semester']}" if pd.notnull(r['Year']) and r['Semester'] else '',
                            axis=1
                        )
                        overall_ts = df_times[['Period', 'Overall - Mean']].dropna()
                        if not overall_ts.empty:
                            overall_ts = overall_ts.groupby('Period')['Overall - Mean'].mean()
                            st.subheader('Overall Rating Over Time')
                            st.line_chart(overall_ts)
                except Exception as e:
                    st.warning(f"Could not generate charts: {e}")
            else:
                st.error("❌ No data could be extracted from the files. Please check the file format.")

# Instructions
with st.expander("ℹ️ How to use"):
    st.markdown("""
    1. **Upload Files**: Click "Browse files" and select one or more HTML evaluation files
    2. **Process**: Click the "Process Files" button to extract data
    3. **Review**: Check the summary statistics and data preview
    4. **Download**: Click "Download CSV" to save the results as a spreadsheet
    
    The application will automatically:
    - Extract all evaluation data from the HTML files
    - Use descriptive column names based on survey items
    - Sort data by year and semester
    - Provide summary statistics
    """)


