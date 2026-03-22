from __future__ import annotations

from collections import defaultdict, deque

from domain.implementation_roadmap import RoadmapDependency, RoadmapItem

from application.readiness.phase_policy import phase_order_index


def build_roadmap_dependencies(items: list[RoadmapItem]) -> list[RoadmapDependency]:
    """Infer prerequisite edges between roadmap items (10B)."""
    deps: list[RoadmapDependency] = []
    if not items:
        return deps

    by_key = {i.item_code: i for i in items}

    sec_f = [i for i in items if i.workstream == "security" and i.phase == "foundation"]
    crm_f = [i for i in items if i.workstream == "crm_integration" and i.phase == "foundation"]
    for c in crm_f:
        for s in sec_f:
            deps.append(
                RoadmapDependency(
                    from_item_code=s.item_code,
                    to_item_code=c.item_code,
                    reason="Security baseline before CRM integration hardening",
                )
            )

    crawl_f = [i for i in items if i.workstream == "crawl" and i.phase == "foundation"]
    for cr in crm_f:
        for w in crawl_f:
            deps.append(
                RoadmapDependency(
                    from_item_code=w.item_code,
                    to_item_code=cr.item_code,
                    reason="Crawl framework before CRM delivery integration",
                )
            )

    foundation_any = [i for i in items if i.phase == "foundation"]
    obs_gl = [i for i in items if i.workstream == "observability" and i.phase == "go_live_baseline"]
    for o in obs_gl:
        for f in foundation_any:
            if f.item_code == o.item_code:
                continue
            deps.append(
                RoadmapDependency(
                    from_item_code=f.item_code,
                    to_item_code=o.item_code,
                    reason="Foundation stack before observability for canary",
                )
            )

    rel_gl = [i for i in items if i.workstream == "release_governance" and i.phase == "go_live_baseline"]
    for r in rel_gl:
        for o in obs_gl:
            deps.append(
                RoadmapDependency(
                    from_item_code=o.item_code,
                    to_item_code=r.item_code,
                    reason="Observability before widening rollout via release gates",
                )
            )

    life_gl = [i for i in items if i.workstream == "lifecycle" and i.phase == "go_live_baseline"]
    for l in life_gl:
        for c in crm_f:
            deps.append(
                RoadmapDependency(
                    from_item_code=c.item_code,
                    to_item_code=l.item_code,
                    reason="CRM transport before lifecycle delivery semantics",
                )
            )

    doc_gl = [i for i in items if i.workstream == "documentation" and i.phase == "go_live_baseline"]
    sup_gl = [i for i in items if i.workstream == "support" and i.phase == "go_live_baseline"]
    for s in sup_gl:
        for d in doc_gl:
            deps.append(
                RoadmapDependency(
                    from_item_code=d.item_code,
                    to_item_code=s.item_code,
                    reason="Store playbooks/docs before support handoff",
                )
            )

    # Merge explicit item.depends_on
    for it in items:
        for prereq in it.depends_on:
            if prereq in by_key and prereq != it.item_code:
                deps.append(
                    RoadmapDependency(
                        from_item_code=prereq,
                        to_item_code=it.item_code,
                        reason="Explicit dependency on roadmap item",
                    )
                )

    # Dedupe (from, to)
    seen: set[tuple[str, str]] = set()
    out: list[RoadmapDependency] = []
    for d in deps:
        k = (d.from_item_code, d.to_item_code)
        if k not in seen and d.from_item_code in by_key and d.to_item_code in by_key:
            seen.add(k)
            out.append(d)
    return out


def infer_critical_path(items: list[RoadmapItem], dependencies: list[RoadmapDependency]) -> list[str]:
    """Longest prerequisite chain (approximate critical path) as ordered item codes."""
    if not items:
        return []
    nodes = {i.item_code for i in items}
    adj: dict[str, list[str]] = defaultdict(list)
    indeg: dict[str, int] = defaultdict(int)
    for d in dependencies:
        if d.from_item_code in nodes and d.to_item_code in nodes:
            adj[d.from_item_code].append(d.to_item_code)
            indeg[d.to_item_code] += 1
            indeg.setdefault(d.from_item_code, 0)
    for n in nodes:
        indeg.setdefault(n, 0)

    indeg_topo = dict(indeg)
    # dp longest path ending at each node (Kahn + relax on outgoing edges)
    dist: dict[str, int] = {n: 0 for n in nodes}
    parent: dict[str, str | None] = {n: None for n in nodes}
    topo: list[str] = []
    q = deque([n for n in nodes if indeg_topo[n] == 0])
    while q:
        u = q.popleft()
        topo.append(u)
        for v in adj[u]:
            indeg_topo[v] -= 1
            if indeg_topo[v] == 0:
                q.append(v)
            cand = dist[u] + 1
            if cand >= dist[v]:
                dist[v] = cand
                parent[v] = u

    if len(topo) < len(nodes):
        # cycle or disconnected — fall back to phase/priority sort
        return _fallback_path(items)

    end = max(nodes, key=lambda n: dist[n])
    chain: list[str] = []
    cur: str | None = end
    while cur is not None:
        chain.append(cur)
        cur = parent.get(cur)  # type: ignore[assignment]
    chain.reverse()
    return chain


def _fallback_path(items: list[RoadmapItem]) -> list[str]:
    return [
        i.item_code
        for i in sorted(
            items,
            key=lambda x: (phase_order_index(x.phase), {"p0": 0, "p1": 1, "p2": 2, "p3": 3}[x.priority], x.item_code),
        )
    ]


def detect_parallelizable_items(
    items: list[RoadmapItem],
    dependencies: list[RoadmapDependency],
) -> list[list[str]]:
    """Layers of items with no prerequisite edge between items in the same layer (parallel streams)."""
    if not items:
        return []
    nodes = {i.item_code for i in items}
    adj: dict[str, list[str]] = defaultdict(list)
    indeg: dict[str, int] = defaultdict(int)
    for d in dependencies:
        if d.from_item_code in nodes and d.to_item_code in nodes:
            adj[d.from_item_code].append(d.to_item_code)
            indeg[d.to_item_code] += 1
    for n in nodes:
        indeg.setdefault(n, 0)

    indeg_layer = dict(indeg)
    layers: list[list[str]] = []
    current = [n for n in nodes if indeg_layer[n] == 0]
    remaining = set(nodes)
    while current:
        layers.append(sorted(current))
        nxt: list[str] = []
        for u in current:
            remaining.discard(u)
            for v in adj[u]:
                indeg_layer[v] -= 1
                if indeg_layer[v] == 0:
                    nxt.append(v)
        current = sorted(set(nxt))

    if remaining:
        layers.append(sorted(remaining))
    return [layer for layer in layers if layer]
