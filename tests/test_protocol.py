import unittest
from amigo.protocol import Assembly,request
from amigo.settings import DEFAULTS
class ProtocolTests(unittest.TestCase):
 def test_policy(self):
  for tools,thinking,limit in [(False,False,1024),(True,False,4096),(False,True,4096)]:
   body=request(DEFAULTS,[],thinking,tools)
   self.assertEqual(body['max_tokens'],limit)
   self.assertEqual(body['provider']['max_price'],{'prompt':.3,'completion':1.2})
   self.assertNotIn('sort',body['provider'])
   self.assertEqual(body['model'],'deepseek/deepseek-v4.1-flash-1017')
 def test_formatting_guidance_preserves_custom_prompt(self):
  custom=DEFAULTS|{'system_prompt':'Instrução personalizada de teste.'}
  prompt=request(custom,[])['messages'][0]['content']
  self.assertTrue(prompt.startswith(custom['system_prompt']))
  self.assertIn('Markdown quando ajudar',prompt)
  self.assertIn('Data e hora de Lisboa',prompt)
 def test_fragmented_calls(self):
  a=Assembly()
  for chunk in [
   {'choices':[{'delta':{'tool_calls':[{'index':0,'id':'c1','function':{'name':'read_','arguments':'{"pa'}}]}}]},
   {'choices':[{'delta':{'tool_calls':[{'index':0,'function':{'name':'file','arguments':'th":"/tmp/ação"}'}}]},'finish_reason':'tool_calls'}]}]:a.accept(chunk)
  self.assertEqual(a.assistant()['tool_calls'][0]['function']['name'],'read_file')
 def test_never_execute_incomplete(self):
  a=Assembly();a.accept({'choices':[{'delta':{'tool_calls':[{'index':0,'id':'a','function':{'name':'read_file','arguments':'{}'}}]}}]})
  with self.assertRaises(ValueError):a.assistant()
 def test_duplicate_call_ids(self):
  a=Assembly();a.accept({'choices':[{'delta':{'tool_calls':[{'index':i,'id':'same','function':{'name':'read_file','arguments':'{}'}} for i in range(2)]},'finish_reason':'tool_calls'}]})
  with self.assertRaises(ValueError):a.assistant()
