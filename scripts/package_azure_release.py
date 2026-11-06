"""Package only release source and the built frontend, never private data/keys."""
import tarfile
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    output = root / ".tmp/azure_pilot/application.tar.gz"
    output.parent.mkdir(parents=True, exist_ok=True)
    if not (root / "web/dist/index.html").is_file():
        raise SystemExit("Run npm ci and npm run build in web first")
    with tarfile.open(output, "w:gz") as archive:
        for name in ["src", "scripts", "prompts", "deployment", "infra", "web/dist",
                     "Dockerfile", "pyproject.toml", "requirements.txt", "README.md", "TO_DO.md", "documentation"]:
            archive.add(root / name, arcname=name, filter=lambda item: None if
                        "__pycache__" in item.name or item.name.endswith(".pyc") else item)
    print("Private release artifact prepared: " + str(output))
