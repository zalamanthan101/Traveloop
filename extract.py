import docx
from PyPDF2 import PdfReader

with open('extracted_docx.txt', 'w', encoding='utf-8') as f:
    try:
        doc = docx.Document('Traveloop_Problems_Guide.docx')
        f.write('\n'.join([p.text for p in doc.paragraphs]))
    except Exception as e:
        f.write(f"Docx Error: {e}")

with open('extracted_pdf.txt', 'w', encoding='utf-8') as f:
    try:
        reader = PdfReader('Traveloop_Project_Suggestions.pdf')
        f.write('\n'.join([p.extract_text() for p in reader.pages]))
    except Exception as e:
        f.write(f"PDF Error: {e}")
