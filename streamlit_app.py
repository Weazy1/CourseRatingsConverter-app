import streamlit as st
import re
import csv
import io
from pathlib import Path
from html import unescape
import pandas as pd

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
    """Process uploaded files and return data."""
    all_data = []
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
                # Remove internal keys
                if '_survey_items' in data:
                    del data['_survey_items']
                if '_filename' in data:
                    del data['_filename']
                all_data.append(data)
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
    
    return all_data, survey_items, processed_count, error_count

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
            all_data, survey_items, processed_count, error_count = process_files(uploaded_files)
            
            if all_data:
                # Create DataFrame
                df = create_dataframe(all_data, survey_items)
                
                # Store in session state
                st.session_state['df'] = df
                st.session_state['survey_items'] = survey_items
                
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
                
                # Download CSV
                st.header("💾 Download Results")
                csv_data = generate_csv(df)
                st.download_button(
                    label="📥 Download CSV",
                    data=csv_data,
                    file_name="evaluations.csv",
                    mime="text/csv"
                )
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


