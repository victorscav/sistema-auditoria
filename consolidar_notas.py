from pathlib import Path
from pypdf import PdfWriter

pasta = Path(__file__).parent / "notas_tecnicas_mangaratiba"
saida = pasta / "CONSOLIDADO_MANGARATIBA.pdf"

pdfs = sorted(p for p in pasta.rglob("*.pdf") if p.name != saida.name)

writer = PdfWriter()
for p in pdfs:
    writer.append(str(p))
    print(f"  + {p.parent.name}/{p.name}")

with open(saida, "wb") as f:
    writer.write(f)

print(f"\nArquivo gerado: {saida}")
print(f"Total de PDFs mesclados: {len(pdfs)}")
