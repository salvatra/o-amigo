"""Chat-completions request policy and fragmented tool-call assembly."""
import copy
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from .tools import schemas


def request(settings, messages, thinking=False, tools=False):
    provider={'allow_fallbacks':settings['allow_fallbacks'],'require_parameters':True,
              'max_price':{'prompt':settings['input_price'],'completion':settings['output_price']}}
    if settings['routing']!='balanced':provider['sort']=settings['routing']
    if settings['providers']:provider['order']=list(settings['providers'])
    prompt=settings['system_prompt']
    if settings['include_time']:prompt+='\nData e hora de Lisboa: '+datetime.now(ZoneInfo('Europe/Lisbon')).isoformat(timespec='seconds')
    body={'model':settings['model'],'stream':True,'provider':provider,'reasoning':{'enabled':thinking},
          'max_tokens':settings['thinking_tokens'] if thinking else settings['tool_tokens'] if tools else settings['simple_tokens'],
          'messages':[{'role':'system','content':prompt},*copy.deepcopy(messages)]}
    if tools:body['tools']=schemas();body['tool_choice']='auto'
    if settings['temperature'] is not None:body['temperature']=settings['temperature']
    return body

class Assembly:
    def __init__(self):
        self.text='';self.calls={};self.reasoning=[];self.usage={};self.provider=None;self.finish=None
    def accept(self, chunk):
        if not isinstance(chunk,dict):raise ValueError('Invalid stream object')
        if chunk.get('error'):raise ValueError('Provider returned an error')
        if chunk.get('usage'):self.usage=chunk['usage']
        if chunk.get('provider'):self.provider=chunk['provider']
        for choice in chunk.get('choices',[]):
            if choice.get('index',0)!=0:continue
            delta=choice.get('delta') or {}
            text=delta.get('content')
            if isinstance(text,str):self.text+=text
            if delta.get('reasoning_details'):self.reasoning.extend(delta['reasoning_details'])
            for part in delta.get('tool_calls',[]):
                index=part.get('index')
                if type(index) is not int or not 0<=index<32:raise ValueError('Invalid tool index')
                call=self.calls.setdefault(index,{'id':'','type':'function','function':{'name':'','arguments':''}})
                if part.get('id'):call['id']+=part['id']
                function=part.get('function') or {}
                for key in ('name','arguments'):
                    value=function.get(key,'')
                    if not isinstance(value,str):raise ValueError('Invalid function fragment')
                    call['function'][key]+=value
                    if len(call['function'][key])>131072:raise ValueError('Oversized function call')
            if choice.get('finish_reason'):self.finish=choice['finish_reason']
    def assistant(self):
        result={'role':'assistant','content':self.text or None}
        if self.reasoning:result['reasoning_details']=self.reasoning
        if self.calls:
            calls=[self.calls[k] for k in sorted(self.calls)]
            if self.finish!='tool_calls':raise ValueError('Incomplete tool-call stream')
            ids=set()
            for call in calls:
                if not call['id'] or call['id'] in ids or not call['function']['name']:raise ValueError('Invalid tool identity')
                ids.add(call['id'])
                args=json.loads(call['function']['arguments'])
                if not isinstance(args,dict):raise ValueError('Tool arguments must be an object')
            result['tool_calls']=calls
        return result
