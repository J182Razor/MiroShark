"""Portable decision memo exports, with the same provenance warnings as the UI."""
from .contracts import SWOTMM


def markdown(run):
    def clean(value): return str(value).replace('<','&lt;').replace('>','&gt;')
    report=run.get('report')
    rows=['# '+clean(report.get('title') if report else run['input']['question']), '',
          '> '+('SYNTHETIC DEMO. ' if run['demo'] else '')+run['notice'], '',
          f"Run: `{run['id']}` | Status: {run['status']} | Created: {run['created_at']}", '',
          '## Question', clean(run['input']['question']), '']
    if not report:
        rows += ['## Review required',clean(run.get('message','No report is available.'))]
    else:
        rows += ['## Executive answer',clean(report['summary']),'','## Recommendation',clean(report['recommendation']),'', '## Alternatives']
        for option in report['options']:
            rows += ['', '### '+clean(option['name']), '**For:** '+clean(option['case_for']),
                     '**Against:** '+clean(option['case_against']), '**Conditions:** '+clean(option['conditions'])]
        for field in ('assumptions','evidence_gaps','decision_triggers'):
            rows += ['', '## '+field.replace('_',' ').title()]
            rows += ['- '+clean(item) for item in report[field]] or ['None reported; this is not proof of completeness.']
        rows += ['','## Risks']
        for item in report['risks']: rows += ['- '+clean(item['risk'])+' Mitigation: '+clean(item['mitigation'])]
        rows += ['','## Next steps']
        for item in report['next_steps']:
            rows += ['- '+clean(item['action']), '  Owner: '+clean(item['owner']),
                     '  Pass check: '+clean(item['success_check']), '  Stop rule: '+clean(item['stop_rule'])]
        rows += ['','## Claims and provenance']
        for item in report['claims']:
            rows += [f"- [{item['kind']}] {clean(item['statement'])} Sources: {', '.join(item['evidence_ids']) or 'inference/assumption'}"]
        rows += ['','## SWOTMM']
        for name in SWOTMM:
            rows += ['','### '+name.title()]+['- '+clean(item) for item in report['swotmm'][name]]
    rows += ['','## Evidence register']
    for source in run.get('evidence',[]):
        rows += [f"- [{source['id']}] {clean(source['title'])} ({source['kind']}); SHA-256 `{source['content_hash']}`."]
        if source.get('coverage'): rows += ['  Coverage: '+clean(source['coverage'])]
    rows += ['','## Validation limits','A threshold pass is a provisional model-judgment gate, not a calibrated probability that this strategy succeeds. No external business actions were executed.']
    if run.get('final_gate'):
        rows += ['','Final raw dimensions:']+[f'- {key}: {value:.4f}' for key,value in run['final_gate']['dimensions'].items()]
    return '\n'.join(rows)+'\n'
