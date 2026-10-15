"""Self-contained HTML report generation for local training history."""

from __future__ import annotations

import html
import json
from collections.abc import Iterable

from dance_mirror.services.analytics import (
    format_duration,
    normalize_records,
    record_package,
    summarize_history,
    top_cue,
    weakest_part,
)
from dance_mirror.services.progression import build_progression
from dance_mirror.storage.database import TrainingRecord


def build_history_report_html(records: Iterable[TrainingRecord]) -> str:
    """Render one portable report without external scripts or network assets."""
    items = normalize_records(records)
    summary = summarize_history(items)
    progression = build_progression(items)
    rows = "\n".join(
        (
            "<tr>"
            f"<td>{html.escape(record.started_at)}</td>"
            f"<td>{html.escape(record_package(record)[1])}</td>"
            f"<td>{record.overall_score:.1f}</td>"
            f"<td>{record.duration_s:.1f} s</td>"
            f"<td>{html.escape(top_cue(record))}</td>"
            f"<td>{html.escape(weakest_part(record))}</td>"
            "</tr>"
        )
        for record in items[:100]
    )
    badges = " / ".join(html.escape(item.label) for item in progression.badges) or "暂无"
    leaderboard = "".join(
        (
            "<li>"
            f"{html.escape(entry.package_name)}"
            f" <strong>{entry.best_score:.1f}</strong>"
            f" <span>{entry.sessions} 次</span>"
            "</li>"
        )
        for entry in progression.leaderboard
    ) or "<li>暂无舞蹈排行</li>"
    snapshot = json.dumps(
        {
            "sessions": summary.sessions,
            "average_score": round(summary.average_score, 2),
            "best_score": round(summary.best_score, 2),
            "stars": progression.stars,
        },
        ensure_ascii=False,
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DanceMirror 训练报告</title>
<style>
body{{margin:0;background:#0b1218;color:#e8f3f8;font:14px/1.5 "Microsoft YaHei UI",sans-serif}}
main{{max-width:1120px;margin:0 auto;padding:36px 24px 56px}}
h1{{font-size:28px;margin:0 0 8px}}h2{{font-size:18px;margin:28px 0 10px}}
p{{color:#9db2be}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
.card,.panel{{background:#111c24;border:1px solid #2a4351;border-radius:8px;padding:14px}}
.card b{{display:block;font-size:24px;color:#39b6d5}}.card span{{color:#9db2be}}
table{{width:100%;border-collapse:collapse;background:#111c24}}
th,td{{padding:9px 10px;border-bottom:1px solid #2a4351;text-align:left}}
th{{color:#9db2be}}ul{{line-height:1.9}}strong{{color:#63dea6}}
@media(max-width:760px){{.cards{{grid-template-columns:repeat(2,1fr)}}table{{font-size:12px}}}}
</style>
</head>
<body><main>
<h1>DanceMirror 训练报告</h1>
<p>本地生成，数据快照：{html.escape(snapshot)}</p>
<section class="cards">
<div class="card"><b>{summary.sessions}</b><span>训练次数</span></div>
<div class="card"><b>{summary.average_score:.1f}</b><span>平均分</span></div>
<div class="card"><b>{summary.best_score:.1f}</b><span>最佳分</span></div>
<div class="card"><b>{format_duration(summary.total_duration_s)}</b><span>累计时长</span></div>
</section>
<section class="panel">
<h2>舞者进度</h2>
<p>{progression.title} · {'★' * progression.stars}{'☆' * (3 - progression.stars)} · 最高连击 {progression.max_combo}</p>
<p>徽章：{badges}</p>
<p>薄弱部位：{html.escape(summary.weakest_part)}；高频问题：{html.escape(summary.top_issue)}</p>
</section>
<section class="panel">
<h2>本地排行榜</h2>
<ul>{leaderboard}</ul>
</section>
<h2>训练明细</h2>
<table>
<thead><tr><th>时间</th><th>舞蹈包</th><th>总分</th><th>时长</th><th>高频问题</th><th>薄弱部位</th></tr></thead>
<tbody>{rows or '<tr><td colspan="6">暂无训练记录</td></tr>'}</tbody>
</table>
</main></body></html>"""
