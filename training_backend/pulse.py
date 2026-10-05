"""Studio bridge to Sentinel's documented Assistant conversation/SSE API.

No action execution endpoints are exposed. Context is a grounding hint, not
an IAM restriction: the engine still governs the authenticated principal.
"""
import hashlib
import json
import threading
import time
import mart

MAX_QUESTION = 4000
MAX_ANSWER = 120000


def consume_sse(response):
    answer=[];steps=[];done=False;event='message';lines=[];size=0;started=time.monotonic()
    def dispatch(name,parts):
        nonlocal done,size
        if not parts:return
        try:data=json.loads('\n'.join(parts))
        except (ValueError,TypeError):raise ValueError('Invalid Assistant stream') from None
        if not isinstance(data,dict):raise ValueError('Invalid Assistant event')
        if name=='error':raise ValueError('Assistant turn failed')
        if name=='delta':
            text=data.get('text')
            if not isinstance(text,str):raise ValueError('Invalid Assistant text')
            size+=len(text)
            if size>MAX_ANSWER:raise ValueError('Assistant answer exceeds limit')
            answer.append(text)
        elif name=='tool_end' and len(steps)<20:
            steps.append({'name':str(data.get('name','Tool'))[:100],'summary':str(data.get('summary',''))[:1000]})
        elif name=='done':done=True
    wire_size=0
    for line in response.iter_lines(decode_unicode=True):
        if time.monotonic()-started>180:raise ValueError('Assistant turn timed out')
        if isinstance(line,bytes):line=line.decode('utf-8')
        wire_size+=len(line)
        if wire_size>2*1024*1024:raise ValueError('Assistant stream exceeds limit')
        if line=='':
            dispatch(event,lines);event='message';lines=[]
        elif line.startswith('event:'):event=line[6:].strip()
        elif line.startswith('data:'):lines.append(line[5:].lstrip())
    dispatch(event,lines)
    if not done or not ''.join(answer).strip():raise ValueError('Assistant did not complete an answer')
    return {'answer':''.join(answer),'tool_steps':steps}


def post_stream(*args,**kwargs):
    import requests
    return requests.post(*args,**kwargs)


class Pulse:
    def __init__(self,client_factory=mart.make_client,snapshot_reader=mart.snapshot,post=post_stream):
        self.client_factory=client_factory;self.snapshot_reader=snapshot_reader;self.post=post
        self.sessions={};self.lock=threading.Lock()
    def status(self,settings,mart_settings):
        if not settings.get('enabled',False):return {'status':'NOT_CONFIGURED','reason':'Ask Pulse connection is not enabled yet.'}
        try:
            # Validate origin, credentials and the Mart map before any remote call.
            mart.query_for(mart_settings)
            client=self.client_factory(mart_settings)
            if not all(hasattr(client,n) for n in ['_get','_post','_headers','api']):raise ValueError('SDK transport unavailable')
            config=client._get('/assistant/config')
            if not isinstance(config,dict):raise ValueError('Invalid Assistant configuration')
            if config.get('enabled') is False:return {'status':'UNAVAILABLE','reason':'The Sentinel Assistant is disabled.'}
            return {'status':'READY','reason':'Assistant API reachable. Published Mart context is required before asking questions.'}
        except Exception:return {'status':'BLOCKED','reason':'Assistant connection failed. Check endpoint, SDK compatibility, credentials and Assistant access.'}
    def reset(self,sid):
        with self.lock:self.sessions.pop(sid,None)
    def ask(self,sid,question,settings,mart_settings,expected_run):
        if not settings.get('enabled',False):raise ValueError('Ask Pulse is not configured')
        if not isinstance(question,str) or not question.strip() or len(question)>MAX_QUESTION:raise ValueError('Enter a question of 1 to 4,000 characters')
        view=self.snapshot_reader(mart_settings)
        if view.get('status')!='CONNECTED':raise ValueError('A verified published Mart view is required before asking Pulse')
        run=view['data']['run']
        if expected_run!=run['run_id']:raise ValueError('Published Mart run changed. Refresh the workspace before asking again.')
        context={'app':'Sentinel Studio','relation':mart_settings['table'],'scoring_run_id':run['run_id'],
                 'data_as_of_ts':run['as_of'],'model_version':run['model_version'],
                 'business_line':view.get('business_line','Postpaid'),'workspace_mode':mart_settings['mode']}
        fingerprint=hashlib.sha256(json.dumps(context,sort_keys=True).encode()).hexdigest()
        with self.lock:
            state=self.sessions.setdefault(sid,{'lock':threading.Lock(),'cid':None,'context':None})
        if not state['lock'].acquire(blocking=False):raise ValueError('An Ask Pulse answer is already running')
        try:
            client=self.client_factory(mart_settings)
            if state['context']!=fingerprint:
                state['cid']=None;state['context']=fingerprint
            if state['cid'] is None:
                created=client._post('/assistant/conversations')
                cid=created.get('id')
                if isinstance(cid,bool) or not isinstance(cid,int) or cid<1:raise ValueError('Invalid Assistant conversation')
                state['cid']=cid
            content=('Studio analysis request. Use the supplied published COM01 Mart and scoring run as context. '
                     'Cite the relations and cutoff behind any figures. Do not treat this context as an IAM grant. '
                     'Do not execute changes; explain any requested action for review in the Dev Assistant.\n\n'
                     'Question: '+question.strip())
            response=self.post(client.api+'/assistant/conversations/'+str(state['cid'])+'/messages',
                               headers={**client._headers(),'Accept':'text/event-stream'},
                               json={'content':content,'strong':False,'context':context},
                               stream=True,timeout=(10,90),allow_redirects=False)
            try:
                if response.status_code!=200:raise ValueError('Assistant request failed')
                result=consume_sse(response)
            finally:response.close()
            return {'status':'ANSWERED',**result,'context':context,'grounding':'ENGINE_GOVERNED_WITH_STUDIO_CONTEXT',
                    'scope_enforced_by_context':False,'actions_executable_in_studio':False}
        except Exception:
            # A partial/uncertain turn is never retried automatically or reused.
            state['cid']=None
            raise ValueError('Pulse could not complete this answer. Check Assistant access, service availability and token budget.') from None
        finally:state['lock'].release()
