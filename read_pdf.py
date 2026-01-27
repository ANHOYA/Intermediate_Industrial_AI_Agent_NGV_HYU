from pypdf import PdfReader
import sys

def read_pdf(path):
    try:
        reader = PdfReader(path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        return f"Error reading PDF: {e}"

if __name__ == "__main__":
    path = "user_file/Initial_technical_specifications.pdf"
    print(read_pdf(path))
