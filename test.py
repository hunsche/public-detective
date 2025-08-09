import os, time, zipfile, mimetypes, pathlib, re
import google.generativeai as genai
from google.api_core.exceptions import GoogleAPIError

API_KEY = ""
ZIP_PATH = "/tmp/43828151000145-1-000068_2025.zip"
MODEL_ID = "gemini-2.5-pro"
OUT_DIR = "/tmp/gemini_files"
MAX_FILES = 50  # ajuste se quiser

ALLOWED_EXT = {
    ".py",
    ".js",
    ".ts",
    ".java",
    ".go",
    ".rb",
    ".rs",
    ".cpp",
    ".c",
    ".cs",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".md",
    ".txt",
    ".ipynb",
    ".sql",
    ".html",
    ".css",
    ".sh",
    ".bat",
    ".ps1",
    ".pdf",
}

genai.configure(api_key=API_KEY)


def wait_active(file_obj, timeout=180):
    t0 = time.time()
    while (
        getattr(file_obj, "state", None) is None
        or getattr(file_obj.state, "name", "") != "ACTIVE"
    ):
        if time.time() - t0 > timeout:
            raise TimeoutError(
                f"{file_obj.name} não ficou ACTIVE em {timeout}s (state={getattr(file_obj, 'state', None)})"
            )
        time.sleep(2)
        file_obj = genai.get_file(file_obj.name)
    return file_obj


def safe_name(name: str) -> str:
    # tira caminhos e caracteres estranhos
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name or "file"


# 1) Extrair arquivos do ZIP para disco
os.makedirs(OUT_DIR, exist_ok=True)
to_upload_paths = []

with zipfile.ZipFile(ZIP_PATH) as z:
    # ordena por tamanho decrescente ou crescente? aqui: crescente para pegar mais arquivos úteis
    entries = sorted(
        [i for i in z.infolist() if not i.is_dir()], key=lambda i: i.file_size
    )
    for info in entries:
        if len(to_upload_paths) >= MAX_FILES:
            break
        ext = (
            ("." + info.filename.rsplit(".", 1)[-1].lower())
            if "." in info.filename
            else ""
        )
        if ext not in ALLOWED_EXT:
            continue
        if info.file_size > 5 * 1024 * 1024:  # 5 MB por arquivo (ajuste)
            continue

        data = z.read(info)
        fname = safe_name(info.filename)
        dest = os.path.join(OUT_DIR, fname)

        # evita sobrescrever: se já existe, adiciona sufixo numérico
        base, ext2 = os.path.splitext(dest)
        k = 1
        while os.path.exists(dest):
            dest = f"{base}_{k}{ext2}"
            k += 1

        with open(dest, "wb") as f:
            f.write(data)
        to_upload_paths.append(dest)

if not to_upload_paths:
    raise RuntimeError("Nenhum arquivo elegível encontrado no ZIP (extensões/limites).")

print(f"Arquivos a enviar: {len(to_upload_paths)}")

# 2) Upload de cada arquivo por path
uploaded_files = []
for p in to_upload_paths:
    mime = mimetypes.guess_type(p)[0] or "text/plain"
    f = genai.upload_file(path=p, mime_type=mime, display_name=pathlib.Path(p).name)
    f = wait_active(f)
    uploaded_files.append(f)
    print(f"ACTIVE: {f.display_name} -> {f.name}")

# 3) Chamar o modelo com todos os arquivos
model = genai.GenerativeModel(MODEL_ID)
prompt = (
    "Analise estes arquivos como se fosse um repositório. "
    "Resuma objetivo do projeto, estrutura de pastas, principais módulos e TODOs imediatos."
)

resp = model.generate_content([prompt, *uploaded_files])
print("\n--- Resposta ---\n")
print(resp.text)
