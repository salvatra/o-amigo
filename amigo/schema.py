"""Small strict validator for the JSON Schema subset used by our closed registry."""
from .policy import Denied

def validate(value,schema,path='arguments'):
    kind=schema.get('type')
    matches={'object':isinstance(value,dict),'array':isinstance(value,list),'string':isinstance(value,str),
             'integer':type(value)is int,'number':type(value)in(int,float),'boolean':type(value)is bool}
    if kind not in matches or not matches[kind]:raise Denied('Invalid '+path+' type')
    if 'enum' in schema and value not in schema['enum']:raise Denied('Invalid '+path+' choice')
    if kind=='object':
        properties=schema.get('properties',{})
        if set(value)-set(properties) or not set(schema.get('required',[]))<=set(value):raise Denied('Invalid '+path+' keys')
        for key,item in value.items():validate(item,properties[key],path+'.'+key)
    elif kind=='array':
        if not schema.get('minItems',0)<=len(value)<=schema.get('maxItems',1000):raise Denied('Invalid '+path+' length')
        for index,item in enumerate(value):validate(item,schema['items'],path+f'[{index}]')
    elif kind=='string':
        if '\x00' in value or not schema.get('minLength',0)<=len(value)<=schema.get('maxLength',4096):raise Denied('Invalid '+path+' length')
    elif kind in ('integer','number'):
        if not schema.get('minimum',-1e100)<=value<=schema.get('maximum',1e100):raise Denied('Invalid '+path+' range')
