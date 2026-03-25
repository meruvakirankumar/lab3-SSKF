#!/usr/bin/env python3
"""Quick fix for diagram generation functions"""

fixed_dependency = '''def _generate_dependency_diagram(files: list[dict], ai_insights: dict | None = None) -> str:
    lines = ["graph LR"]
    nodes_added: set[str] = set()
    edges: set[str] = set()
    edge_count = 0
    for f in files[:20]:
        if edge_count >= 25:
            break
        src = _sanitize_mermaid_id(f["file_path"])
        src_label = Path(f["file_path"]).name
        for imp in f.get("imports", [])[:2]:
            if edge_count >= 25:
                break
            dst = _sanitize_mermaid_id(imp)
            if src and dst and src != dst:
                if src not in nodes_added:
                    lines.append(f'  {src}["{src_label}"]')
                    nodes_added.add(src)
                if dst not in nodes_added:
                    lines.append(f'  {dst}["{dst[:20]}"]')
                    nodes_added.add(dst)
                edges.add(f"  {src} --> {dst}")
                edge_count += 1
    lines.extend(sorted(edges))
    if len(lines) == 1:
        lines.append("  A[No dependencies]")
        lines.append("  B[Check source files]")
        lines.append("  A --> B")
    return "\\n".join(lines)


def _generate_flowchart_diagram(files: list[dict], ai_insights: dict | None = None) -> str:
    lines = ["flowchart TD"]
    if not files:
        lines.append("  start([No source files found])")
        lines.append("  start --> end([Upload a codebase])")
        return "\\n".join(lines)
    chain = files[:10]
    for idx, file_info in enumerate(chain):
        node_id = f"n{idx}"
        label = Path(file_info["file_path"]).name
        label = label.replace('"', '')
        lines.append(f'  {node_id}["{label}"]')
    for idx in range(len(chain) - 1):
        lines.append(f"  n{idx} --> n{idx + 1}")
    if ai_insights and "architecture_pattern" in ai_insights and len(chain) > 0:
        pattern = ai_insights.get("architecture_pattern", "Unknown")
        pattern = pattern.replace('"', '').replace("'", '')
        lines.append(f'  pattern["{pattern} Pattern"]')
        lines.append(f"  n0 --> pattern")
    return "\\n".join(lines)'''

print(fixed_dependency)
