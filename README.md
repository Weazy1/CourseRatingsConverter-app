# 📊 Instructor Evaluation Parser

A Streamlit web application that parses HTML instructor evaluation files and extracts structured data for analysis. The app processes evaluation surveys, extracts key metrics (ratings, response rates, statistics), and generates CSV files with descriptive column names for easy analysis.

## Features

- **Batch Processing**: Upload and process multiple HTML evaluation files at once
- **Data Extraction**: Automatically extracts:
  - Course information (code, name, semester, year)
  - Instructor details
  - Enrollment numbers
  - Survey item statistics (means, standard deviations, response rates)
  - Overall ratings and percentages
- **CSV Export**: Download processed data as a CSV file with descriptive column names
- **Visual Summaries**: Automatic generation of:
  - Bar chart showing average item means (per survey question)
  - Line chart showing overall rating trends over time (by semester and year)
- **Summary Statistics**: Quick overview metrics including total evaluations, year range, average ratings, and total enrollment

## How to Run Locally

### Prerequisites

- Python 3.7 or higher
- pip (Python package installer)

### Setup Instructions

1. **Navigate to the project directory**

   ```powershell
   cd "C:\Users\wesfl\OneDrive\Documents\Angie Review\CourseRatingsConverter-app-1"
   ```

2. **Create a virtual environment (recommended)**

   ```powershell
   py -m venv venv
   ```

3. **Activate the virtual environment**

   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

   *Note: If you get an execution policy error, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` first*

4. **Install dependencies**

   ```powershell
   pip install -r requirements.txt
   ```

5. **Run the app**

   ```powershell
   streamlit run streamlit_app.py
   ```

6. **Open in browser**

   The app will automatically open in your default browser at `http://localhost:8501`. If it doesn't, navigate to that URL manually.

### Running Again Later

Once you've set up the virtual environment, you only need to:

1. Activate the virtual environment:
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

2. Run the app:
   ```powershell
   streamlit run streamlit_app.py
   ```

## Usage

1. **Upload Files**: Click "Browse files" and select one or more HTML evaluation files
2. **Process**: Click the "Process Files" button to extract data
3. **Review**: Check the summary statistics and data preview
4. **Download**: Click "Download CSV" to save the results as a spreadsheet
5. **Visualize**: View the "Quick Visual Summary" section for charts showing:
   - Average item means across all survey questions
   - Overall rating trends over time

The application automatically:
- Extracts all evaluation data from HTML files
- Uses descriptive column names based on survey items
- Sorts data by year and semester
- Provides summary statistics and visualizations

## Testing Changes

- The app automatically reloads when you save changes to `streamlit_app.py`
- Refresh your browser to see updates
- Check the terminal for any error messages
