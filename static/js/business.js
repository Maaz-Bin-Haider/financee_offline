/* Local company identity for presentation/exports. Never transforms financial data. */
(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory;
  if(root&&root.document){var node=root.document.getElementById('financee-business');root.FinanceeBusiness=factory(node?JSON.parse(node.textContent):{},root);}
}(typeof window!=='undefined'?window:null,function(config,root){
  'use strict';
  var name=String(config.name||'Financee'), zone=String(config.timezone||'UTC'), money=config.currency||{};
  function escape(value){return String(value||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
  function stamp(date){return new Intl.DateTimeFormat('en-GB',{timeZone:zone,dateStyle:'medium',timeStyle:'medium',hour12:false}).format(date||new Date())+' '+zone;}
  function today(date){var parts=new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(date||new Date());var values={};parts.forEach(function(p){values[p.type]=p.value;});return values.year+'-'+values.month+'-'+values.day;}
  function calendar(date){return new Date(today(date)+'T12:00:00Z');}
  function dateLabel(value,options){
    var raw=String(value||''),only=/^\d{4}-\d{2}-\d{2}$/.test(raw);
    var date=only?new Date(raw+'T12:00:00Z'):(value?new Date(value):new Date());
    return new Intl.DateTimeFormat('en-GB',Object.assign({day:'2-digit',month:'short',year:'numeric'},options||{},{timeZone:only?'UTC':zone})).format(date);
  }
  function range(which,date){
    if(!['today','7d','30d','mtd','ytd','this_month','last_month','this_year'].includes(which))return {};
    var end=calendar(date),start=new Date(end),year=end.getUTCFullYear(),month=end.getUTCMonth();
    if(which==='7d')start.setUTCDate(start.getUTCDate()-7);
    else if(which==='30d')start.setUTCDate(start.getUTCDate()-30);
    else if(which==='mtd'||which==='this_month')start=new Date(Date.UTC(year,month,1,12));
    else if(which==='ytd'||which==='this_year')start=new Date(Date.UTC(year,0,1,12));
    else if(which==='last_month'){start=new Date(Date.UTC(year,month-1,1,12));end=new Date(Date.UTC(year,month,0,12));}
    return {from:start.toISOString().slice(0,10),to:end.toISOString().slice(0,10)};
  }
  function metadata(){return [['Company',name],['Address',config.address||''],['Phone',config.phone||''],['Email',config.email||''],['Currency',money.code||''],['Display label',money.label||''],['Currency symbol',money.symbol||''],['Timezone',zone],['Generated',stamp()]];}
  function csvCell(value){var text=String(value==null?'':value);if(/^[=+@-]/.test(text))text="'"+text;return '"'+text.replace(/"/g,'""')+'"';}
  function csvPrefix(){if(root&&root.financeeFeatureEnabled&&!root.financeeFeatureEnabled('excel_export'))throw new Error('CSV export is disabled in local General Settings.');return '\ufeff'+metadata().map(function(row){return row.map(csvCell).join(',');}).join('\n')+'\n\n';}
  function printHeader(){return '<header class="financee-print-header"><h2>'+escape(name)+'</h2><p>'+escape(config.address)+'</p><p>'+escape([config.phone,config.email].filter(Boolean).join(' · '))+'</p><p>Currency: '+escape(money.code)+' · '+escape(money.label)+' · '+escape(money.symbol)+' · '+escape(zone)+'</p></header>';}
  function printStyles(){var link=root&&root.document.getElementById('financee-business-style');return link?'<link rel="stylesheet" href="'+escape(link.href)+'">':'';}
  function preparePDF(doc,kind){
    if(root&&root.financeeFeatureEnabled&&!root.financeeFeatureEnabled("pdf_export",kind||"reports"))throw new Error("PDF export is disabled in local General Settings.");
    if(doc._financeePrepared)return doc;
    doc._financeePrepared=true;
    var fonts=root&&root.FinanceePdfFonts;
    if(!fonts||!doc.addFileToVFS)throw new Error('Local PDF fonts are unavailable. Reload Financee before exporting.');
    Object.keys(fonts).forEach(function(style){var file='FinanceeSans-'+style+'.ttf';doc.addFileToVFS(file,fonts[style]);doc.addFont(file,'FinanceeSans',style);});
    var setFont=doc.setFont.bind(doc),getFont=doc.getFont.bind(doc);
    function alias(font){return ['helvetica','times','courier'].includes(String(font).toLowerCase())?'FinanceeSans':font;}
    doc.setFont=function(font,style,weight){return setFont(alias(font),style,weight);};
    doc.getFont=function(font,style,options){return font?getFont(alias(font),style,options):getFont();};
    doc.setFont('FinanceeSans','normal');
    doc.setProperties({author:name,creator:'Financee Offline',subject:'Currency '+money.code+' | '+zone});
    var scale=doc.internal.scaleFactor||1;
    var width=doc.internal.pageSize.getWidth(),margin=28/scale;
    doc.setFontSize(6.5);
    var footer=[];
    [name,config.address,[config.phone,config.email].filter(Boolean).join(' · '),
     'Currency: '+money.code+' · '+zone,'Display label: '+money.label+' · Symbol: '+money.symbol].filter(Boolean).forEach(function(line){footer=footer.concat(doc.splitTextToSize(String(line),width-2*margin));});
    doc._financeeFooterLines=footer;doc._financeeFooterPoints=Math.max(76,footer.length*8+22);
    doc.setFontSize(16);
    if(doc.autoTable){var auto=doc.autoTable.bind(doc);doc.autoTable=function(options){
      options=Object.assign({},options);
      ['styles','headStyles','bodyStyles','footStyles'].forEach(function(key){options[key]=Object.assign({},options[key],{font:'FinanceeSans'});});
      var m=options.margin;if(typeof m==='number')m={left:m,right:m,top:m,bottom:m};
      options.margin=Object.assign({},m,{bottom:Math.max(m&&m.bottom||0,(doc._financeeFooterPoints+8)/scale)});
      return auto(options);
    };}
    var save=doc.save.bind(doc);
    doc.save=function(){finalizePDF(doc);return save.apply(doc,arguments);};
    return doc;
  }
  function invoiceIdentity(doc,x,y,width,height){
    var size=doc.getFontSize(),font=size,lines;
    do{doc.setFontSize(font);lines=doc.splitTextToSize(name,width);if(lines.length*font*1.15/doc.internal.scaleFactor<=height)break;font-=.5;}while(font>=5.5);
    doc.text(lines,x,y);doc.setFontSize(size);return {lines:lines,font:font,height:lines.length*font*1.15/doc.internal.scaleFactor};
  }
  function finalizePDF(doc){
    if(doc._financeeFinalized)return doc;
    doc._financeeFinalized=true;
    var scale=doc.internal.scaleFactor||1, count=doc.internal.getNumberOfPages(),current=doc.internal.getCurrentPageInfo().pageNumber;
    for(var page=1;page<=count;page++){
      doc.setPage(page);var width=doc.internal.pageSize.getWidth(),height=doc.internal.pageSize.getHeight(),margin=28/scale;
      var band=doc._financeeFooterPoints;
      doc.setFillColor(255,255,255);doc.rect(0,height-band/scale,width,band/scale,'F');
      doc.setDrawColor(210,218,230);doc.setLineWidth(.4/scale);doc.line(margin,height-(band-2)/scale,width-margin,height-(band-2)/scale);
      doc.setTextColor(45,57,75);doc.setFont('FinanceeSans','normal');doc.setFontSize(6.5);
      var y=height-(band-13)/scale;doc._financeeFooterLines.forEach(function(line){doc.text(line,margin,y);y+=8/scale;});
      doc.setFontSize(5.5);doc.text('Financee Offline · '+stamp(),margin,height-7/scale);doc.text('Page '+page+' / '+count,width-margin,height-7/scale,{align:'right'});
    }
    doc.setPage(current);return doc;
  }
  return Object.freeze({name:name,timezone:zone,stamp:stamp,today:today,calendar:calendar,dateLabel:dateLabel,range:range,csvPrefix:csvPrefix,metadata:metadata,printHeader:printHeader,printStyles:printStyles,preparePDF:preparePDF,invoiceIdentity:invoiceIdentity,finalizePDF:finalizePDF,bodyBottom:function(doc){return doc.internal.pageSize.getHeight()-((doc._financeeFooterPoints||76)+12)/(doc.internal.scaleFactor||1);}});
}));
