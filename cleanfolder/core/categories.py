from pathlib import Path


CATEGORIES = {
    "Word": (".doc", ".docx", ".docm", ".dot", ".dotx", ".odt"),
    "PowerPoint": (".ppt", ".pptx", ".pptm", ".pps", ".ppsx", ".odp"),
    "Excel": (".xls", ".xlsx", ".xlsm", ".xlsb", ".csv", ".ods"),
    "PDF": (".pdf",),
    "Images": (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".svg", ".bmp", ".tif", ".tiff", ".avif", ".ico"),
    "Videos": (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv"),
    "Audio": (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".aiff", ".wma"),
    "Archives": (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz"),
    "Installers": (".dmg", ".pkg", ".msi", ".exe", ".iso"),
    "Code": (".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".html", ".css", ".scss", ".json", ".yaml", ".yml", ".toml", ".xml", ".sql", ".sh", ".ipynb"),
    "Text": (".txt", ".md", ".markdown", ".rtf", ".log", ".rst", ".tex"),
    "Others": (),
}

EXTENSIONS = {extension: category for category, extensions in CATEGORIES.items() for extension in extensions}


def classify(name: str) -> str:
    return EXTENSIONS.get(Path(name).suffix.lower(), "Others")
