import os
import xml.etree.ElementTree as ET
from datetime import datetime
import pdfplumber
from odf import text, teletype

KEYWORDS = {
    'milestone': 'milestone',
    'task': 'task',
    'todo': 'todo',
    'build_note': 'build note',
    'status': 'status',
    'open': 'open',
    'pending': 'pending'
}

PROJECT_MAPPINGS = {
    'bankit': 'Bankit',
    'project_bankit': 'Bankit',
    'Desktop': 'UntitledProject Crew',
    'Documents': 'Various Projects',
    'ai builder': 'AI Builder',
    'awittivations': 'Awittivations',
    'BRF': 'BRF',
    'forge-std': 'Forge Std',
    'icm-contracts': 'ICM Contracts',
    'launchlayer': 'Launchlayer',
    'noncustodial-teleporter': 'Noncustodial Teleporter',
    'openzeppelin-contracts': 'OpenZeppelin Contracts',
}

SCAN_FOLDERS = [
    '/home/jack/Documents',
    '/home/jack/Desktop',
    '/home/jack/bankit',
    '/home/jack/project_bankit',
    '/home/jack/launchlayer',
    '/home/jack/awittivations',
    '/home/jack/icm-contracts',
    '/home/jack/project-dashboard',
]

SKIP_DIRS = {'venv', 'node_modules', '__pycache__', '.git', 'env', 'bankit-env', 'CMakeFiles'}

def get_project_name(path):
    for folder, project in PROJECT_MAPPINGS.items():
        if folder in path:
            return project
    parts = path.split('/')
    for part in reversed(parts):
        if part and part not in ['home', 'jack']:
            return part.replace('_', ' ').title()
    return 'General'

def extract_text_from_pdf(file_path):
    result = ''
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    result += page_text + '\n'
    except Exception as e:
        print(f"Error reading PDF {file_path}: {e}")
    return result

def extract_text_from_odt(file_path):
    try:
        doc = text.load(file_path)
        return teletype.extractText(doc)
    except Exception as e:
        print(f"Error reading ODT {file_path}: {e}")
        return ''

def extract_text_from_md(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading MD {file_path}: {e}")
        return ''

def extract_text_from_txt(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading TXT {file_path}: {e}")
        return ''

def get_xml_namespace(tag):
    if tag.startswith('{'):
        return tag[1:tag.index('}')]
    return ''

def extract_iso_20022(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
    except Exception as e:
        print(f"Error parsing XML {file_path}: {e}")
        return []

    namespace = get_xml_namespace(root.tag)
    if not namespace:
        namespace = 'urn:iso:std:iso:20022:tech:xsd:camt.053.001.08'

    ns = {'ns': namespace}
    entries = []

    for entry in root.findall('.//ns:Ntry', ns):
        amount_el = entry.find('.//ns:Amt', ns)
        direction_el = entry.find('.//ns:CdtDbtInd', ns)
        booking_date_el = entry.find('.//ns:BookgDt//ns:Dt', ns)
        amount = amount_el.text if amount_el is not None else 'N/A'
        direction = direction_el.text if direction_el is not None else 'N/A'
        booking_date = booking_date_el.text if booking_date_el is not None else 'N/A'
        label = 'Credit' if direction == 'CRDT' else 'Debit'

        entries.append({
            'project': get_project_name(file_path),
            'type': 'iso20022',
            'content': f"{label} {amount} on {booking_date}",
            'file': file_path,
            'date': datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
        })

    return entries

def extract_items(content, file_path):
    items = []
    lines = content.split('\n')
    for line in lines:
        line_lower = line.lower()
        for key, keyword in KEYWORDS.items():
            if keyword in line_lower:
                items.append({
                    'project': get_project_name(file_path),
                    'type': key,
                    'content': line.strip(),
                    'file': file_path,
                    'date': datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
                })
                break
    return items

def scan_documents():
    extensions = ['.pdf', '.odt', '.odm', '.md', '.txt', '.xml']
    all_items = []

    for folder in SCAN_FOLDERS:
        if not os.path.exists(folder):
            continue
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in SKIP_DIRS]
            for filename in filenames:
                if not any(filename.lower().endswith(ext) for ext in extensions):
                    continue
                file_path = os.path.join(dirpath, filename)
                if os.path.getsize(file_path) > 10 * 1024 * 1024:
                    continue
                try:
                    if filename.lower().endswith('.pdf'):
                        all_items.extend(extract_items(extract_text_from_pdf(file_path), file_path))
                    elif filename.lower().endswith(('.odt', '.odm')):
                        all_items.extend(extract_items(extract_text_from_odt(file_path), file_path))
                    elif filename.lower().endswith('.md'):
                        all_items.extend(extract_items(extract_text_from_md(file_path), file_path))
                    elif filename.lower().endswith('.txt'):
                        all_items.extend(extract_items(extract_text_from_txt(file_path), file_path))
                    elif filename.lower().endswith('.xml'):
                        all_items.extend(extract_iso_20022(file_path))
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")

    return all_items

if __name__ == '__main__':
    items = scan_documents()
    print(f"Extracted {len(items)} items")
    for item in items[:5]:
        print(item)
