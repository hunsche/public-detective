import pdfplumber

with pdfplumber.open("/tmp/file_attachments/anexo/Avaliação de estratégia de ranking.pdf") as pdf:
    for page in pdf.pages:
        print(page.extract_text())
