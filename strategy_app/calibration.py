"""Evaluate externally labeled, held-out validator cases; never self-certify a run."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from .contracts import probability


def evaluate(cases, threshold=.95):
    threshold=probability(threshold)
    if not isinstance(cases,list) or not cases: raise ValueError('Provide labeled held-out cases')
    parsed=[]
    for case in cases:
        if type(case.get('label')) is not bool: raise ValueError('Each label must be a human/reference boolean')
        parsed.append((probability(case.get('score')),int(case['label'])))
    accepted=[label for score,label in parsed if score>=threshold]
    n=len(accepted); precision=sum(accepted)/n if n else None
    lower=None
    if n:
        z=1.959963984540054
        lower=(precision+z*z/(2*n)-z*math.sqrt(precision*(1-precision)/n+z*z/(4*n*n)))/(1+z*z/n)
    bins=[];ece=0
    for index in range(10):
        subset=[(p,y) for p,y in parsed if min(int(p*10),9)==index]
        if not subset: continue
        mean=sum(p for p,y in subset)/len(subset); observed=sum(y for p,y in subset)/len(subset)
        ece+=len(subset)/len(parsed)*abs(mean-observed)
        bins.append({'bin':index,'count':len(subset),'mean_score':mean,'observed_positive_rate':observed})
    return {'n':len(parsed),'threshold':threshold,'accepted':n,'coverage':n/len(parsed),
            'accepted_case_precision':precision,'precision_lower_95':lower,
            'brier':sum((p-y)**2 for p,y in parsed)/len(parsed),'ece_10_bins':ece,'bins':bins,
            'reliability_claim':'none',
            'limitations':'Evaluation only. Use representative independent held-out labels for one fixed validator/domain/model version. These metrics do not certify arbitrary strategies or automatically change production gates.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases',help='JSONL with score:number and label:boolean per case')
    parser.add_argument('--threshold',type=float,default=.95)
    parser.add_argument('--validator',required=True)
    parser.add_argument('--model',required=True)
    args=parser.parse_args()
    try:
        raw=Path(args.cases).read_bytes()
        cases=[json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
        result=evaluate(cases,args.threshold)
    except (ValueError,OSError,KeyError,TypeError) as exc: parser.error(str(exc))
    result.update(validator=args.validator,model=args.model,dataset_sha256=hashlib.sha256(raw).hexdigest())
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__': main()
