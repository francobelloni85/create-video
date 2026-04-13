import json
import csv
import sys
import re
import os
import glob

def find_social_content(data):
    """Recursively search for the exact 'social_content' key."""
    if isinstance(data, dict):
        if 'social_content' in data:
            return str(data['social_content']).strip()
        for value in data.values():
            result = find_social_content(value)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_social_content(item)
            if result:
                return result
    return None

def extract_gdrive_id(url):
    """Extracts the unique ID from a Google Drive link."""
    # Match standard format: https://drive.google.com/file/d/FILE_ID/view...
    match = re.search(r'/file/d/([a-zA-Z0-9_-]+)(?:/|$|\?)', url)
    if match:
        return match.group(1)
    # Match alternative format: https://drive.google.com/open?id=FILE_ID
    match = re.search(r'id=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return None

def get_lesson_number(filename):
    """Extract lesson number for correct numerical sorting."""
    match = re.search(r'(\d+)', os.path.basename(filename))
    return int(match.group(1)) if match else 0

def main():
    lessons_dir = "input_lessons"
    links_path = os.path.join(lessons_dir, "links.csv")
    csv_path = "metricool_autolist.csv"

    # Fallback if links.csv is in the current directory
    if not os.path.exists(links_path) and os.path.exists("links.csv"):
        links_path = "links.csv"

    # 1. Read Links Mapping
    links_dict = {}
    try:
        with open(links_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None) # Skip header row
            for row in reader:
                if len(row) >= 2:
                    filename = row[0].strip()
                    link = row[1].strip()
                    lesson_num = get_lesson_number(filename)
                    if lesson_num > 0:
                        file_id = extract_gdrive_id(link)
                        if file_id:
                            links_dict[lesson_num] = f"https://drive.google.com/uc?export=download&id={file_id}"
                        else:
                            links_dict[lesson_num] = link # fallback if not extracted
    except FileNotFoundError:
        print(f"Error: CSV file '{links_path}' not found.")
        sys.exit(1)

    # 2. Read all JSON files
    if not os.path.exists(lessons_dir):
        print(f"Error: Directory '{lessons_dir}' not found.")
        sys.exit(1)

    # Sort files numerically
    json_files = glob.glob(os.path.join(lessons_dir, "*.json"))
    json_files.sort(key=get_lesson_number)

    output_rows = []
    
    for json_file in json_files:
        lesson_num = get_lesson_number(json_file)
        
        # Match current JSON with its corresponding link
        if lesson_num not in links_dict:
            print(f"Warning: No link found for lesson {lesson_num} in CSV.")
            continue

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            content = find_social_content(data)
            if content:
                link = links_dict[lesson_num]
                output_rows.append([content, link])
            else:
                print(f"Warning: 'social_content' key not found in {json_file}")
        except Exception as e:
            print(f"Error reading {json_file}: {e}")

    print(f"Found {len(json_files)} JSON files and {len(links_dict)} links.")
    print(f"Successfully matched and processing {len(output_rows)} items...")
        
    # 3. Output Generation
    try:
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            for row in output_rows:
                writer.writerow(row)
        print(f"Success! Created '{csv_path}' with {len(output_rows)} rows.")
    except Exception as e:
        print(f"Error writing to CSV: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
