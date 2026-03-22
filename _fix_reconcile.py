from pathlib import Path

p = Path("infrastructure/pipelines/sync_pipeline.py")
lines = p.read_text(encoding="utf-8").splitlines(True)
# Find "        try:" after tok_rec start_stage and indent until "        finally:"
start = None
end = None
for i, line in enumerate(lines):
    if line.strip() == "try:" and i > 0 and "tok_rec" in lines[i - 1]:
        start = i
    if start is not None and line.strip().startswith("finally:") and "finish_stage" in lines[i + 1]:
        end = i
        break
if start is None or end is None:
    raise SystemExit(f"markers not found start={start} end={end}")

# Lines start+1 to end-1 should be inside try - add 4 spaces to lines that are at 8 spaces
# Actually lines after try that are not indented enough - the broken block
new_lines = lines[: start + 1]
for j in range(start + 1, end):
    line = lines[j]
    if line.strip() == "":
        new_lines.append(line)
        continue
    # If line starts with 8 spaces (method body level) but not 12, it should be in try body
    if line.startswith("        ") and not line.startswith("            "):
        new_lines.append("    " + line)
    else:
        new_lines.append(line)
new_lines.extend(lines[end:])
p.write_text("".join(new_lines), encoding="utf-8")
print("done", start, end)
