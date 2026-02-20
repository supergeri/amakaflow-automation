"""Trace viewer HTML generator.

Generates an interactive HTML/JS page for viewing captured sessions
and their diffs across the pipeline.
"""

import html
import json
from pathlib import Path
from typing import Any


def generate_viewer_html(capture_dir: Path, session_name: str) -> str:
    """Generate an interactive trace viewer HTML page for a session.
    
    Args:
        capture_dir: Root directory containing capture sessions
        session_name: Name of the session to view
        
    Returns:
        Complete HTML string
    """
    # Load session data
    from .replay import load_session, replay_session
    
    session_dir = capture_dir / session_name
    snapshots = load_session(capture_dir, session_name)
    result = replay_session(capture_dir, session_name)
    
    # Convert to JSON-safe format
    snapshots_json = json.dumps([
        {
            "capture_point": s.capture_point,
            "endpoint": s.endpoint,
            "method": s.method,
            "timestamp": s.timestamp,
            "request_payload": s.request_payload,
            "response_payload": s.response_payload,
            "response_status": s.response_status,
        }
        for s in snapshots
    ], default=str)
    
    diffs_json = json.dumps([
        {
            "path": d.path,
            "type": d.diff_type,
            "old_value": d.old_value,
            "new_value": d.new_value,
        }
        for d in result.diffs
    ], default=str)
    
    # Escape </script> tags to prevent breaking out of script context
    snapshots_json = snapshots_json.replace("</script>", "<\\/script>")
    diffs_json = diffs_json.replace("</script>", "<\\/script>")
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trace Viewer - {html.escape(session_name)}</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #1a1a2e;
            color: #eee;
            line-height: 1.6;
        }}
        
        .header {{
            background: #16213e;
            padding: 20px;
            border-bottom: 2px solid #0f3460;
        }}
        
        .header h1 {{
            color: #00d9ff;
            font-size: 1.5rem;
        }}
        
        .status {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 4px;
            font-weight: bold;
            margin-left: 10px;
        }}
        
        .status.clean {{
            background: #28a745;
            color: white;
        }}
        
        .status.corrupted {{
            background: #dc3545;
            color: white;
        }}
        
        .container {{
            display: flex;
            min-height: calc(100vh - 80px);
        }}
        
        .timeline {{
            width: 280px;
            background: #16213e;
            padding: 20px;
            border-right: 1px solid #0f3460;
            overflow-y: auto;
        }}
        
        .timeline h2 {{
            color: #00d9ff;
            font-size: 1rem;
            margin-bottom: 15px;
        }}
        
        .hop {{
            padding: 12px;
            margin-bottom: 8px;
            background: #0f3460;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
            border-left: 3px solid transparent;
        }}
        
        .hop:hover {{
            background: #1a4a7a;
        }}
        
        .hop.active {{
            border-left-color: #00d9ff;
            background: #1a4a7a;
        }}
        
        .hop.has-diff {{
            border-left-color: #dc3545;
        }}
        
        .hop-name {{
            font-weight: bold;
            color: #fff;
        }}
        
        .hop-endpoint {{
            font-size: 0.8rem;
            color: #888;
            margin-top: 4px;
        }}
        
        .main {{
            flex: 1;
            padding: 20px;
            overflow-y: auto;
        }}
        
        .section {{
            background: #16213e;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        
        .section h3 {{
            color: #00d9ff;
            margin-bottom: 15px;
            border-bottom: 1px solid #0f3460;
            padding-bottom: 10px;
        }}
        
        .json-viewer {{
            background: #0f0f23;
            border-radius: 6px;
            padding: 15px;
            overflow-x: auto;
            max-height: 400px;
            overflow-y: auto;
        }}
        
        .json-viewer pre {{
            margin: 0;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 0.85rem;
            color: #a0a0a0;
        }}
        
        .diff-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        .diff-table th, .diff-table td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #0f3460;
        }}
        
        .diff-table th {{
            background: #0f3460;
            color: #00d9ff;
        }}
        
        .diff-type {{
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.8rem;
        }}
        
        .diff-type.added {{
            background: #28a745;
            color: white;
        }}
        
        .diff-type.removed {{
            background: #dc3545;
            color: white;
        }}
        
        .diff-type.changed {{
            background: #ffc107;
            color: black;
        }}
        
        .diff-type.type_changed {{
            background: #17a2b8;
            color: white;
        }}
        
        .old-value {{
            color: #ff6b6b;
            text-decoration: line-through;
        }}
        
        .new-value {{
            color: #69db7c;
        }}
        
        .arrow {{
            color: #666;
            margin: 0 8px;
        }}
        
        .summary {{
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        .summary-card {{
            background: #0f3460;
            padding: 15px 25px;
            border-radius: 8px;
            text-align: center;
        }}
        
        .summary-card .value {{
            font-size: 2rem;
            font-weight: bold;
            color: #00d9ff;
        }}
        
        .summary-card .label {{
            font-size: 0.85rem;
            color: #888;
            margin-top: 5px;
        }}
        
        .corruption-warning {{
            background: #dc3545;
            color: white;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .corruption-warning .icon {{
            font-size: 1.5rem;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>
            Trace Viewer: {html.escape(session_name)}
            <span class="status {'clean' if result.is_clean else 'corrupted'}">
                {'✓ CLEAN' if result.is_clean else '✗ CORRUPTED'}
            </span>
        </h1>
    </div>
    
    <div class="container">
        <div class="timeline">
            <h2>Pipeline Timeline</h2>
            <div id="hops">
                {''.join(_render_hops(snapshots, result))}
            </div>
        </div>
        
        <div class="main">
            {f'<div class="corruption-warning"><span class="icon">⚠</span> First corruption at: <strong>{html.escape(result.first_corruption_hop)}</strong></div>' if result.first_corruption_hop else ''}
            
            <div class="summary">
                <div class="summary-card">
                    <div class="value">{len(snapshots)}</div>
                    <div class="label">Snapshots</div>
                </div>
                <div class="summary-card">
                    <div class="value">{len(result.diffs)}</div>
                    <div class="label">Diffs Found</div>
                </div>
                <div class="summary-card">
                    <div class="value">{len(set(s.capture_point for s in snapshots))}</div>
                    <div class="label">Pipeline Hops</div>
                </div>
            </div>
            
            <div class="section" id="details">
                <h3>Request/Response Details</h3>
                <p style="color: #888;">Click a hop on the timeline to view details</p>
            </div>
            
            <div class="section">
                <h3>All Diffs ({len(result.diffs)})</h3>
                {render_diffs_table(result.diffs)}
            </div>
        </div>
    </div>
    
    <script>
        const snapshots = {snapshots_json};
        const diffs = {diffs_json};
        
        function showHop(index) {{
            // Update active state
            document.querySelectorAll('.hop').forEach((el, i) => {{
                el.classList.toggle('active', i === index);
            }});
            
            const snap = snapshots[index];
            const details = document.getElementById('details');
            
            // Find diffs for this hop
            const hopName = snap.capture_point;
            const hopDiffs = diffs.filter(d => d.path.includes(hopName));
            
            let diffHtml = '';
            if (hopDiffs.length > 0) {{
                diffHtml = `
                    <h4 style="color: #dc3545; margin-top: 15px;">Diffs at this hop:</h4>
                    ${{renderDiffs(hopDiffs)}}
                `;
            }}
            
            details.innerHTML = `
                <h3>${{snap.capture_point}}</h3>
                <p><strong>Endpoint:</strong> ${{snap.method}} ${{snap.endpoint}}</p>
                <p><strong>Status:</strong> ${{snap.response_status}}</p>
                
                <h4 style="color: #00d9ff; margin-top: 15px;">Request Payload:</h4>
                <div class="json-viewer">
                    <pre>${{JSON.stringify(snap.request_payload, null, 2)}}</pre>
                </div>
                
                <h4 style="color: #00d9ff; margin-top: 15px;">Response Payload:</h4>
                <div class="json-viewer">
                    <pre>${{JSON.stringify(snap.response_payload, null, 2)}}</pre>
                </div>
                
                ${{diffHtml}}
            `;
        }}
        
        function renderDiffs(hopDiffs) {{
            if (hopDiffs.length === 0) return '<p style="color: #28a745;">No diffs at this hop</p>';
            
            return '<table class="diff-table"><tr><th>Path</th><th>Type</th><th>Change</th></tr>' +
                hopDiffs.map(d => `
                    <tr>
                        <td>${{d.path}}</td>
                        <td><span class="diff-type ${{d.type}}">${{d.type}}</span></td>
                        <td>
                            ${{d.old_value !== null ? '<span class="old-value">' + JSON.stringify(d.old_value).substring(0, 50) + '</span>' : ''}}
                            ${{d.old_value !== null && d.new_value !== null ? '<span class="arrow">→</span>' : ''}}
                            ${{d.new_value !== null ? '<span class="new-value">' + JSON.stringify(d.new_value).substring(0, 50) + '</span>' : ''}}
                        </td>
                    </tr>
                `).join('') + '</table>';
        }}
        
        // Click handlers for hops
        document.querySelectorAll('.hop').forEach((el, index) => {{
            el.addEventListener('click', () => showHop(index));
        }});
        
        // Show first hop by default
        if (snapshots.length > 0) {{
            showHop(0);
        }}
    </script>
</body>
</html>"""


def _render_hops(snapshots: list, result) -> list[str]:
    """Render hop timeline items."""
    from .replay import DEFAULT_PIPELINE_STAGES
    
    hops_html = []
    seen = set()
    
    for snap in snapshots:
        if snap.capture_point in seen:
            continue
        seen.add(snap.capture_point)
        
        # Check if this hop has diffs
        has_diff = any(d.path.startswith(snap.capture_point) for d in result.diffs)
        
        hops_html.append(f"""
            <div class="hop {'has-diff' if has_diff else ''}">
                <div class="hop-name">{snap.capture_point}</div>
                <div class="hop-endpoint">{snap.method} {snap.endpoint}</div>
            </div>
        """)
    
    return hops_html


def render_diffs_table(diffs: list) -> str:
    """Render diffs as an HTML table."""
    if not diffs:
        return '<p style="color: #28a745;">No differences found - pipeline is clean!</p>'
    
    rows = []
    for d in diffs:
        old_val = str(d.old_value)[:50] if d.old_value is not None else ""
        new_val = str(d.new_value)[:50] if d.new_value is not None else ""
        
        rows.append(f"""
            <tr>
                <td>{d.path}</td>
                <td><span class="diff-type {d.diff_type}">{d.diff_type}</span></td>
                <td>
                    {f'<span class="old-value">{old_val}</span>' if old_val else ''}
                    {f'<span class="arrow">→</span>' if old_val and new_val else ''}
                    {f'<span class="new-value">{new_val}</span>' if new_val else ''}
                </td>
            </tr>
        """)
    
    return f"""
        <table class="diff-table">
            <tr>
                <th>Path</th>
                <th>Type</th>
                <th>Change</th>
            </tr>
            {''.join(rows)}
        </table>
    """
