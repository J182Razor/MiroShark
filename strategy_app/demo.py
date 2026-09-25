"""Explicit synthetic fixture. Never selected as a fallback for live failures."""
from copy import deepcopy
from .contracts import SWOTMM

DEMO_QUESTION = 'Should we pilot a managed lead-response service before building a standalone SaaS?'


def demo_plan():
    actions=[('A1','Compare strategic alternatives',[]),('A2','Identify the decision-critical uncertainties',['A1']),
             ('A3','Specify a bounded validation test',['A2'])]
    return {'outcome_contract':{'desired_outcome':'Choose a reversible next step for a lead-response offering',
        'actor_or_owner':'User','environment':'Illustrative business scenario',
        'success_observable':'A conditional decision memo with alternatives and a measurable test',
        'failure_observable':'Treating an untested assumption as customer demand',
        'constraints':['No automatic spending or customer outreach'],
        'prohibited_actions':['external business side effects'], 'deadline_or_sla':'Not specified',
        'required_evidence':['Customer need and delivery observations'], 'reversible_actions':['Create analysis artifacts'],
        'irreversible_actions':[], 'human_approval_boundaries':['Approve the analysis plan']},
        'assumptions':['Demand, delivery cost and renewal behavior have not been measured.'],
        'questions':['Which prospect segment has a recurring unresolved lead-response problem?'],
        'atoms':[{'id':identifier,'objective':action,'action':action,'object':'Supplied question and predecessor analysis',
            'executor':'lower_tier','dependencies':deps,'evidence_ids':['E_INPUT'],
            'postcondition':'Specific conditional finding, explicit gaps, and an observable next check',
            'failure_path':'human_review','side_effect':'none'} for identifier,action,deps in actions]}


def demo_report():
    return {'title':'Validate the service before funding the product',
        'summary':'Synthetic example: start with a bounded managed-service pilot, provided a specific prospect confirms the problem. The available scenario does not establish demand, willingness to pay or delivery economics.',
        'recommendation':'Use the pilot to observe whether your team can resolve a repeatable lead-response problem. Build a standalone product only after customers use the service and the full delivery cost is known. Do not treat a simulation or a Jev score as purchase evidence.',
        'options':[
            {'name':'Managed-service pilot','case_for':'Direct observation of the workflow before committing to product scope.',
             'case_against':'Manual support and exceptions may limit scale.','conditions':'A suitable prospect agrees to a narrow, measurable pilot.','is_status_quo':False},
            {'name':'Build standalone SaaS now','case_for':'Potentially reusable delivery if the problem and workflow are already proven.',
             'case_against':'Upfront scope and acquisition risk are unresolved.','conditions':'Repeated demand and stable delivery requirements are independently established.','is_status_quo':False},
            {'name':'Keep current workflow','case_for':'Avoid new implementation and support obligations.',
             'case_against':'Any actual response backlog remains unaddressed.','conditions':'No sufficiently valuable or recurring problem is confirmed.','is_status_quo':True}],
        'claims':[{'statement':'The requested choice is between a managed service and a standalone product.',
                   'kind':'user_supplied','evidence_ids':['E_INPUT']}],
        'assumptions':['A narrow client workflow can be isolated without production-wide changes.'],
        'evidence_gaps':['Obtain current response volume, missed-response examples, owner approval and full delivery costs.',
                         'Ask the intended customer what outcome would justify paying and renewing.'],
        'risks':[{'risk':'A polished demo is mistaken for customer demand.','mitigation':'Use actual customer participation and independently reviewed operational results.'},
                 {'risk':'Support work expands beyond the agreed pilot.','mitigation':'Fix the scope and record every exception.'}],
        'next_steps':[{'action':'Choose one customer workflow and document its current results.','owner':'User',
                       'success_check':'Baseline records and a responsible reviewer are available.','stop_rule':'Stop if access or authorization is missing.'},
                      {'action':'Run a reversible pilot with a predefined evaluation period.','owner':'Pilot owner',
                       'success_check':'Compare response quality and total labor, including review and rework.','stop_rule':'Pause if errors exceed the agreed tolerance.'}],
        'decision_triggers':['Choose the SaaS path only when repeated customer use and stable requirements justify it.',
                             'Stop or change the offer if no suitable customer confirms the problem.'],
        'swotmm':{
            'strengths':['A bounded service pilot can use an existing delivery workflow.'],
            'weaknesses':['Demand and fully loaded delivery costs remain unmeasured.'],
            'opportunities':['Repeated customer problems may reveal reusable product requirements.'],
            'threats':['Premature product scope and unbounded support can consume resources.'],
            'moats':['Permissioned corrected examples and documented delivery expertise may become useful assets.'],
            'monetization':['Test a clearly scoped paid service only after confirming the promised deliverable; no revenue is predicted.']}}


class DemoModel:
    def generate(self, policy, state):
        if 'TASK: REPAIR.' in policy: return deepcopy(state['plan'])
        if 'TASK: PLAN.' in policy: return demo_plan()
        if 'TASK: REPORT.' in policy: return demo_report()
        action=state['atom']['action']
        return {'summary':f'Synthetic finding for: {action}. Favor a reversible experiment while demand and operational effort remain unknown.',
                'claims':[],'assumptions':['This fixture is illustrative, not measured evidence.'],
                'evidence_gaps':['Collect independently reviewed customer and workflow observations.']}


class DemoJev:
    score=.99
    def decide(self,state,questions):
        return {'model':'synthetic-jev-fixture','answers':{key:{'type':'noul','noul':self.score} for key in questions},'usage':{}}


class DemoClients:
    def __init__(self):
        self.frontier=DemoModel(); self.executor=DemoModel(); self.jev=DemoJev(); self.miro=None
        self.identity={'frontier':'synthetic-planner-fixture','executor':'synthetic-executor-fixture','jev':'synthetic-jev-fixture'}
