import json,unittest
from types import SimpleNamespace
from unittest.mock import Mock
from pulse import Pulse,consume_sse
from test_mart import settings,payload


def stream(events):
    response=Mock(status_code=200)
    lines=[]
    for name,data in events:lines+=['event: '+name,'data: '+json.dumps(data),'']
    response.iter_lines.return_value=iter(lines);return response


def view():return {'status':'CONNECTED','business_line':'Postpaid','data':payload()}


class PulseChecks(unittest.TestCase):
    def setUp(self):
        self.client=SimpleNamespace(api='https://dev.sentinel.inalpha.ai/api/v1',_get=Mock(return_value={'enabled':True}),_post=Mock(side_effect=[{'id':1},{'id':2},{'id':3}]),_headers=lambda:{'Authorization':'Bearer test-secret'})
        self.post=Mock(side_effect=lambda *a,**k:stream([('delta',{'text':'20 high-risk subscribers.'}),('tool_end',{'name':'query','summary':'Read the configured Mart'}),('done',{'tokens':20})]))
        self.reader=Mock(return_value=view());self.bridge=Pulse(lambda _:self.client,self.reader,self.post)
    def ask(self,sid='s',run='published'):return self.bridge.ask(sid,'How many are high risk?',{'enabled':True},settings(),run)
    def test_documented_transport_and_context(self):
        result=self.ask();self.assertEqual(result['status'],'ANSWERED');self.assertEqual(result['answer'],'20 high-risk subscribers.');self.assertFalse(result['scope_enforced_by_context']);self.assertFalse(result['actions_executable_in_studio'])
        args,kwargs=self.post.call_args;self.assertTrue(args[0].endswith('/assistant/conversations/1/messages'));self.assertEqual(kwargs['json']['context']['relation'],settings()['table']);self.assertFalse(kwargs['allow_redirects']);self.assertNotIn('test-secret',json.dumps(result))
    def test_session_and_run_isolation_and_reset(self):
        self.ask();self.ask();self.assertEqual(self.client._post.call_count,1)
        self.ask('other');self.assertEqual(self.client._post.call_count,2)
        self.reader.return_value['data']['run']['run_id']='new-run';self.ask(run='new-run');self.assertEqual(self.client._post.call_count,3)
        self.bridge.reset('s');self.assertNotIn('s',self.bridge.sessions)
    def test_no_published_mart_and_stale_view_block_remote_calls(self):
        with self.assertRaisesRegex(ValueError,'changed'):self.ask(run='stale')
        self.reader.return_value={'status':'NOT_CONFIGURED'}
        with self.assertRaisesRegex(ValueError,'published'):self.ask()
        self.client._post.assert_not_called();self.post.assert_not_called()
    def test_disabled_and_invalid_questions_block(self):
        with self.assertRaisesRegex(ValueError,'configured'):self.bridge.ask('s','q',{},settings(),'published')
        for q in [None,'','x'*4001]:
            with self.assertRaises(ValueError):self.bridge.ask('s',q,{'enabled':True},settings(),'published')
        self.assertEqual(self.bridge.status({},settings())['status'],'NOT_CONFIGURED')
    def test_stream_errors_incomplete_and_limits_fail_closed(self):
        for response in [stream([('delta',{'text':'partial'})]),stream([('error',{'message':'sensitive-secret'})]),stream([('delta',{'text':'x'*120001}),('done',{})])]:
            with self.assertRaises(ValueError):consume_sse(response)
        self.post.side_effect=RuntimeError('credential-or-token-in-url')
        with self.assertRaises(ValueError) as raised:self.ask()
        self.assertNotIn('credential-or-token',str(raised.exception));self.assertIsNone(self.bridge.sessions['s']['cid'])
    def test_status_reports_api_readiness_only(self):
        self.assertEqual(self.bridge.status({'enabled':True},settings())['status'],'READY')
        self.client._get.return_value={'enabled':False};self.assertEqual(self.bridge.status({'enabled':True},settings())['status'],'UNAVAILABLE')
        self.client._get.side_effect=RuntimeError('sensitive-secret');status=self.bridge.status({'enabled':True},settings());self.assertEqual(status['status'],'BLOCKED');self.assertNotIn('sensitive-secret',json.dumps(status))
    def test_parallel_turn_rejected(self):
        self.ask();self.bridge.sessions['s']['lock'].acquire()
        try:
            with self.assertRaisesRegex(ValueError,'already running'):self.ask()
        finally:self.bridge.sessions['s']['lock'].release()
