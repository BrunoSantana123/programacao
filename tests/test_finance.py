"""Executa o mesmo módulo financeiro importado pelo Edge Runtime, sem rede."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]


class FinanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module=(ROOT/'supabase/functions/nexo-mcp-test/finance.mjs').as_uri()
        source='''
import {balance,listMovements,queryArguments,receipt} from MODULE;
const fixture={entries:[
 {id:'old',date:'2026-11-01',uber:100.10,noventa:2,fuel:10,reserve:5,description:'Legado'},
 {id:'new',date:'2026-11-02',type:'income',category:'Salário',amount:250.15,description:'Receita'},
 {id:'expense',date:'2026-11-02',type:'expense',category:'Comida',amount:32.5,description:'Despesa'},
 {id:'reserve',date:'2026-11-03',type:'reserve',category:'Viagem',amount:20},
 {id:'release',date:'2026-11-03',type:'release',category:'Viagem',amount:3}
],settings:{private:'never-return'},tasks:[{secret:'never-return'}]};
const before=JSON.stringify(fixture);
const rejects=fn=>{try{fn();return false}catch{return true}};
const body={p_id:'receipt',p_tipo:'despesa',p_centavos:3250,p_categoria:'Comida',p_descricao:'Despesa',p_data:'2026-11-02'};
const saved={lancamento:{id:'receipt',type:'expense',amount:32.5,category:'Comida',description:'Despesa',date:'2026-11-02'},repetido:false};
const result={
 balance:balance(fixture,{}),
 period:balance(fixture,queryArguments({data_inicio:'2026-11-02',data_fim:'2026-11-02'})),
 list:listMovements(fixture,queryArguments({limite:2,pagina:1},true)),
 second:listMovements(fixture,queryArguments({limite:2,pagina:2},true)),
 category:listMovements(fixture,queryArguments({categoria:'  comida ',tipo:'despesa'},true)),
 empty:balance({},{}),
 unchanged:before===JSON.stringify(fixture),
 rejectedArgs:[{user_id:'other'},{data_inicio:'2026-02-30'},{data_inicio:'2026-12-01',data_fim:'2026-01-01'},{pagina:0},{limite:51},{tipo:'transferencia'},{categoria:' '},[],null].map(a=>rejects(()=>queryArguments(a,true))),
 badDocuments:[{entries:{}},{entries:[null]},{entries:[{type:'income',amount:'NaN'}]},{entries:[{type:'income',amount:1e20}]}].map(d=>rejects(()=>balance(d,{}))),
 receipt:receipt(saved,body),
 badReceipts:[{...saved,repetido:undefined},{...saved,lancamento:{...saved.lancamento,id:'other'}},{...saved,lancamento:{...saved.lancamento,amount:33}},{...saved,lancamento:{...saved.lancamento,amount:'32.5'}}].map(s=>rejects(()=>receipt(s,body))),
 noPrivate:!JSON.stringify(listMovements(fixture,queryArguments({},true))).includes('never-return'),
 badDatePeriod:rejects(()=>balance({entries:[{type:'income',amount:1}]},{data_inicio:'2026-11-01'}))
};
console.log(JSON.stringify(result));
'''.replace('MODULE',json.dumps(module))
        result=subprocess.run(['node','--input-type=module','-e',source],capture_output=True,text=True,check=True)
        cls.values=json.loads(result.stdout)

    def test_legacy_and_current_balance_match_app(self):
        b=self.values['balance']
        self.assertEqual([b[k] for k in ['receitas_centavos','despesas_centavos','reservas_centavos','resgates_centavos','saldo_centavos']], [35225,4250,2500,300,28775])
    def test_date_range_inclusive(self): self.assertEqual(self.values['period']['saldo_centavos'],21765)
    def test_pagination_and_stable_order(self):
        self.assertEqual([x['id'] for x in self.values['list']['movimentacoes']],['reserve','release'])
        self.assertEqual([x['id'] for x in self.values['second']['movimentacoes']],['new','expense'])
        self.assertTrue(self.values['list']['tem_mais'])
    def test_filters(self):
        self.assertEqual(self.values['category']['total'],1)
        self.assertEqual(self.values['category']['movimentacoes'][0]['valor_centavos'],3250)
    def test_empty(self): self.assertEqual(self.values['empty']['saldo_centavos'],0)
    def test_no_mutation(self): self.assertTrue(self.values['unchanged'])
    def test_injection_and_bad_inputs(self): self.assertTrue(all(self.values['rejectedArgs']))
    def test_malformed_money_fails_closed(self): self.assertTrue(all(self.values['badDocuments']))
    def test_valid_receipt(self): self.assertEqual(self.values['receipt']['lancamento']['amount'],32.5)
    def test_no_false_confirmation(self): self.assertTrue(all(self.values['badReceipts']))
    def test_only_financial_fields(self): self.assertTrue(self.values['noPrivate'])
    def test_unknown_date_cannot_silently_change_period_balance(self): self.assertTrue(self.values['badDatePeriod'])
