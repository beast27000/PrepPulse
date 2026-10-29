"""PrepPulse Architecture Diagram Exporter.

Fetches and exports the official architecture diagram in PNG and SVG formats.
Usage:
    python scripts/export_diagram.py
"""

from __future__ import annotations

import base64
import urllib.request
from pathlib import Path

DIAGRAM_MMD = """flowchart TD
    subgraph DataLayer [Data Layer]
        OCR[Stage 1 Raw OCR / MongoDB]
        Retriever[Hybrid BM25 + Dense RAG]
    end

    subgraph AgenticSwarm [Agentic Swarm LangGraph]
        Classifier[Patient Classification Agent]
        Trajectory[Metabolic Trajectory Agent]
        CareGaps[Care Gaps Agent]
        Mismatches[Record Mismatches Agent]
        PriorityAgent[Priority Findings Agent]
        CaregiverAgent[Dynamic Caregiver Prep / Handoff Agent]
        ChatAgent[Interactive Chat Dock Agent]
        Compiler[Brief Compiler]
    end

    subgraph UIPresentationLayer [UI Presentation Layer]
        Cards[Top 4 Dynamic Consultation Cards]
        Tiles[Priority Findings Tiles Reverse Chronological]
        Proof[Source Proof Panel 0-1000 Bounding Box]
        ChatUI[Interactive Clinical Chat Dock]
        LangToggle[Multi-Lingual Toggle EN / HI / TA]
    end

    OCR --> Retriever
    Retriever --> Classifier
    Classifier --> Trajectory
    Classifier --> CareGaps
    Classifier --> Mismatches
    Classifier --> PriorityAgent
    Classifier --> CaregiverAgent
    Trajectory --> Cards
    CareGaps --> Cards
    Mismatches --> Cards
    PriorityAgent --> Tiles
    CaregiverAgent --> LangToggle
    Retriever --> ChatAgent
    ChatAgent --> ChatUI
    Cards --> Proof
    Tiles --> Proof
    Compiler --> Cards
    Compiler --> Tiles"""


def export_diagrams() -> None:
    output_dir = Path(__file__).resolve().parent.parent / "docs"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Save raw MMD
    mmd_path = output_dir / "architecture_diagram.mmd"
    mmd_path.write_text(DIAGRAM_MMD, encoding="utf-8")
    print(f"Saved MMD: {mmd_path}")

    # 2. Fetch and save SVG
    svg_encoded = base64.urlsafe_b64encode(DIAGRAM_MMD.encode("utf-8")).decode("ascii")
    svg_url = f"https://mermaid.ink/svg/{svg_encoded}"
    req_svg = urllib.request.Request(svg_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req_svg, timeout=15) as resp:
        svg_data = resp.read()
    svg_path = output_dir / "architecture_diagram.svg"
    svg_path.write_bytes(svg_data)
    print(f"Saved SVG: {svg_path} ({len(svg_data)} bytes)")

    # 3. Fetch and save PNG
    png_encoded = base64.b64encode(DIAGRAM_MMD.encode("utf-8")).decode("ascii")
    png_url = f"https://mermaid.ink/img/{png_encoded}"
    req_png = urllib.request.Request(png_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req_png, timeout=15) as resp:
        png_data = resp.read()
    png_path = output_dir / "architecture_diagram.png"
    png_path.write_bytes(png_data)
    print(f"Saved PNG: {png_path} ({len(png_data)} bytes)")


if __name__ == "__main__":
    export_diagrams()
