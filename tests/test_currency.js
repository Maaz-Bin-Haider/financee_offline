"use strict";
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname,'..');
const money = require(path.join(root,'static/js/currency.js'));
const business = require(path.join(root,'static/js/business.js'))({timezone:'UTC'});
let count=0;
function check(name,fn){fn();count++;console.log('PASS:',name);}
check('AED amount label uses saved code and two decimal precision',()=>assert.equal(money({code:'AED'}).format('1234.5'),'AED 1,234.50'));
check('USD and EUR labels do not inherit PKR',()=>{assert.equal(money({code:'USD'}).format(0),'USD 0.00');assert.equal(money({code:'EUR'}).format(-25.5),'EUR -25.50');});
check('display override is separate from the real currency',()=>{const m=money({code:'AED',symbol:'Dhs',label:'Dhs'});assert.equal(m.code,'AED');assert.equal(m.format(15),'Dhs 15.00');});
check('Unicode symbol override is preserved',()=>assert.equal(money({code:'EUR',symbol:'€',label:'€'}).format(12.25),'€ 12.25'));
check('ISO currency minor units do not change original display precision',()=>assert.equal(money({code:'JPY'}).format('12.50'),'JPY 12.50'));
check('empty configuration never invents a PKR base currency',()=>assert.equal(money({}).format(0),'0.00'));
check('large negative and zero chart axes use selected label',()=>{const m=money({code:'AED'});assert.equal(m.axis(12000),'AED 12k');assert.equal(m.axis(-25),'AED -25');assert.equal(m.axis(0),'AED 0');});
function dashboard(config){
 const elements=new Map();const pdfs=[];let chart;
 function el(id){if(!elements.has(id))elements.set(id,{textContent:'',innerHTML:'',value:'',style:{},events:{},addEventListener(n,fn){this.events[n]=fn;},querySelector(){return {textContent:'',innerHTML:'',style:{}};},getContext(){return {};},toDataURL(){return 'data:image/png;base64,test';}});return elements.get(id);}
 const responses={
 '/home/api/dash/sales/chart/':[{label:'Oct 1',revenue:'1234.50',profit:'234.50'}],
 '/home/api/dash/sales/today/':{sales_today:'1234.50',profit_today:'234.50',invoice_count:1},
 '/home/api/cash/':{cash_balance:'500.25'},
 '/home/api/dash/expenses/kpi/':{today:'12.50',this_month:'25.00',this_year:'50.00'}
 };
 class PDF{constructor(){this.tables=[];pdfs.push(this);this.lastAutoTable={finalY:30};}setFontSize(){}setTextColor(){}text(){}autoTable(t){this.tables.push(t);}addImage(){}addPage(){}save(){}}
 const context=vm.createContext({console,Intl,Date,URLSearchParams,encodeURIComponent,setTimeout,clearTimeout,
 document:{cookie:'',body:{style:{}},addEventListener(){},getElementById:el,querySelectorAll(){return [];},querySelector(){return null;}},
 window:{FinanceeMoney:money(config),FinanceeBusiness:{...business,preparePDF:doc=>doc},jspdf:{jsPDF:PDF}},localStorage:{getItem(){return null;},setItem(){}},
 Chart:class{constructor(ctx,opts){chart=opts;}destroy(){}},
 fetch:async url=>({ok:true,json:async()=>({status:'ok',data:responses[url.split('?')[0]]})})});
 vm.runInContext(fs.readFileSync(path.join(root,'static/js/home_script.js'),'utf8'),context);
 return {context,elements,pdfs,get chart(){return chart;}};
}
(async()=>{
 for(const config of [{code:'AED'},{code:'USD'},{code:'EUR',label:'€'}]){
  const d=dashboard(config);const label=config.label||config.code;
  await vm.runInContext('Promise.all([loadSalesToday(),loadSalesChart("7d"),loadCashBalance(),loadExpenseKpi()])',d.context);
  check(label+' dashboard cards and chart summary use the saved currency',()=>{
   assert.equal(d.elements.get('kpi-sales-today').textContent,label+' 1,234.50');
   assert.equal(d.elements.get('kpi-profit-today').textContent,label+' 234.50');
   assert.equal(d.elements.get('kpi-cash-balance').textContent,label+' 500.25');
   assert.equal(d.elements.get('kpi-expense-today').textContent,label+' 12.50');
   assert.equal(d.elements.get('chart-total-revenue').textContent,label+' 1,234.50');
  });
  check(label+' real chart tooltip and axis callbacks use saved currency',()=>{
   assert.equal(d.chart.options.plugins.tooltip.callbacks.label({dataset:{label:'Revenue'},parsed:{y:1234.5}}),' Revenue: '+label+' 1,234.50');
   assert.equal(d.chart.options.scales.y.ticks.callback(12000),label+' 12k');
  });
  await d.elements.get('chart-pdf-btn').events.click();
  check(label+' dashboard PDF data uses the same currency and amounts',()=>{
   assert.equal(d.pdfs[0].tables[0].body[0][1],label+' 1,234.50');
   assert.equal(d.pdfs[0].tables[1].body[0][1],label+' 1,234.50');
  });
 }
 const d=dashboard({code:'AED',label:'<img>'});
 check('custom display labels are escaped in generated HTML',()=>assert.equal(vm.runInContext('moneyHtml(12)',d.context),'&lt;img&gt; 12.00'));
 console.log(count+' currency regression checks passed');
})().catch(err=>{console.error(err);process.exitCode=1;});
