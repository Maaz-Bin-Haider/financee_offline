"use strict";
// Run with NODE_PATH pointing at developer-only jspdf 2.5.1 / autotable 3.5.31.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),out=path.join(root,'.runtime/test/Exports');fs.mkdirSync(out,{recursive:true});
const factory=require(path.join(root,'static/js/business.js'));
let checks=0;function check(name,fn){fn();checks++;console.log('PASS:',name);}
const cfg={name:'Example Devices & Accounts',address:'Office 12, Main Street, Dubai',phone:'+971 50 1234567',email:'accounts@example.test',timezone:'Asia/Dubai',currency:{code:'AED',symbol:'د.إ',label:'Dhs'}};
check('metadata keeps accounting code, symbol and cosmetic label separate',()=>{const data=Object.fromEntries(factory(cfg).metadata());assert.equal(data.Currency,'AED');assert.equal(data['Display label'],'Dhs');assert.equal(data['Currency symbol'],'د.إ');});
check('business dates honor midnight in the selected timezone',()=>{assert.equal(factory(cfg).today(new Date('2026-10-26T20:30:00Z')),'2026-10-27');assert.equal(factory({...cfg,timezone:'America/New_York'}).today(new Date('2026-10-26T02:00:00Z')),'2026-10-25');});
check('ranges use the business calendar across month/year boundaries',()=>{assert.deepEqual(factory(cfg).range('this_month',new Date('2026-10-31T22:30:00Z')),{from:'2026-11-01',to:'2026-11-01'});assert.deepEqual(factory(cfg).range('last_month',new Date('2026-12-31T22:30:00Z')),{from:'2026-12-01',to:'2026-12-31'});});
check('all-time reports keep an unbounded date range',()=>assert.deepEqual(factory(cfg).range('all'),{}));
check('calendar-only dates are never shifted by a timezone',()=>assert.equal(factory({...cfg,timezone:'America/Los_Angeles'}).dateLabel('2026-10-26'),'26 Oct 2026'));
check('CSV metadata is quoted and spreadsheet-formula-safe',()=>{const text=factory({...cfg,name:'=2+2',address:'Comma, "quoted"\naddress'}).csvPrefix();assert(text.startsWith('\ufeff'));assert(text.includes('"Company","\'=2+2"'));assert(text.includes('"Comma, ""quoted""\naddress"'));});
check('local availability blocks direct PDF/CSV export calls',()=>{const disabled=factory(cfg,{financeeFeatureEnabled:()=>false});assert.throws(()=>disabled.csvPrefix(),/disabled/);assert.throws(()=>disabled.preparePDF({}),/disabled/);});
check('print identity is escaped as text',()=>{const text=factory({...cfg,name:'<script>alert(1)</script>'}).printHeader();assert(text.includes('&lt;script&gt;'));assert(!text.includes('<script>'));});
(async()=>{
 const {jsPDF}=require('jspdf');require('jspdf-autotable');
 const fontWorld={};vm.runInNewContext(fs.readFileSync(path.join(root,'static/js/pdf_fonts.js'),'utf8'),{window:fontWorld});
 const longBusiness=factory({...cfg,name:'M'.repeat(150),address:'Wide address '.repeat(23).slice(0,300),email:'a'.repeat(180)+'@example.test'},fontWorld);
 const longDoc=new jsPDF();longBusiness.preparePDF(longDoc);
 check('long identity details reserve enough footer space',()=>{assert(longDoc._financeeFooterPoints>=longDoc._financeeFooterLines.length*8+22);assert(longBusiness.bodyBottom(longDoc)<270);});
 let identityLines;const text=longDoc.text.bind(longDoc);longDoc.text=function(lines){identityLines=lines;return text.apply(longDoc,arguments);};
 const identity=longBusiness.invoiceIdentity(longDoc,14,26,85,11);
 check('long invoice company names fit the reserved header area',()=>{assert(Array.isArray(identityLines));assert(identityLines.join('').replace(/ /g,'').length===150);assert(identity.height<=11);});
 for(const [code,symbol] of [['AED','د.إ'],['EUR','€'],['PKR','₨'],['BDT','৳']]){
  const blobs=[];const config={...cfg,currency:{code,symbol,label:symbol}};
  const world={};vm.runInNewContext(fs.readFileSync(path.join(root,'static/js/pdf_fonts.js'),'utf8'),{window:world});
  world.FinanceeBusiness=factory(config,world);
  world.FinanceeMoney={label:symbol,code,symbol};
  world.jspdf={jsPDF:class {constructor(...args){const doc=new jsPDF(...args);doc.save=function(){fs.writeFileSync(path.join(out,'phase2_'+code+'.pdf'),Buffer.from(doc.output('arraybuffer')));};return doc;}}};
  const document={addEventListener(){},createElement(){return {click(){},remove(){}};},body:{appendChild(){}}};
  const sandbox=vm.createContext({window:world,document,Intl,Date,console,Blob,URL:{createObjectURL(blob){blobs.push(blob);return 'blob:test';},revokeObjectURL(){}}});
  vm.runInContext(fs.readFileSync(path.join(root,'static/js/owner_equity.js'),'utf8'),sandbox);
  vm.runInContext("_oeRows=Array.from({length:150},(_,i)=>({txn_date:'2026-10-26',direction:i%2?'withdrawal':'injection',account:'Owner capital',amount:1234.50,description:'Export verification row '+(i+1)}));_oeSummary={total_injections:92587.5,total_withdrawals:92587.5,net_contributed:0};oeExportPDF();oeExportCSV();",sandbox);
  const csv=await blobs[0].text();fs.writeFileSync(path.join(out,'phase2_'+code+'.csv'),csv);
  check(code+' actual owner-equity CSV keeps raw numeric amounts and local identity',()=>{assert(csv.includes('"Currency","'+code+'"'));assert(csv.includes('"Currency symbol","'+symbol+'"'));assert(csv.includes('"1234.5"'));assert(csv.includes('"-1234.5"'));});
  check(code+' real PDF generator embeds fonts and local company metadata',()=>{const data=fs.readFileSync(path.join(out,'phase2_'+code+'.pdf'),'latin1');assert(data.startsWith('%PDF-'));assert(data.includes('/FontFile2'));assert(data.includes('Example Devices'));});
 }
 console.log(checks+' company/export checks passed. Real sample artifacts: '+out);
})().catch(error=>{console.error(error);process.exitCode=1;});
