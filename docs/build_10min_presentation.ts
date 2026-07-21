import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const ROOT = process.cwd();
const OUT = path.join(ROOT, "docs", "10분_발표_예시.pptx");
const QA = path.join(ROOT, "docs", "presentation_qa");
const A = path.join(ROOT, "docs", "presentation_assets");
const IMG = path.join(ROOT, "docs", "portfolio", "img");

const C = {
  ivory: "#FBFBF8", ink: "#1B241D", green: "#13301C", leaf: "#2E9E57",
  lime: "#A8C66C", pale: "#EAF3EC", muted: "#66706A", line: "#D9E1DA",
  amber: "#C96B29", white: "#FFFFFF", soft: "#F2F5F1", darkPale: "#C9D6CC",
};

async function bytes(file: string): Promise<ArrayBuffer> {
  const b = await fs.readFile(file);
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
}

function box(slide: any, x: number, y: number, w: number, h: number, fill = C.white, radius = "rounded-xl", line = C.line) {
  return slide.shapes.add({ geometry: "roundRect", position: { left: x, top: y, width: w, height: h }, fill,
    line: { style: "solid", fill: line, width: 1 }, borderRadius: radius });
}

function text(slide: any, value: string, x: number, y: number, w: number, h: number, size = 24, color = C.ink, bold = false, align: any = "left") {
  const s = slide.shapes.add({ geometry: "textbox", position: { left: x, top: y, width: w, height: h }, fill: "none",
    line: { style: "solid", fill: "none", width: 0 } });
  s.text = value;
  s.text.style = { fontSize: size, color, bold, alignment: align, fontFamily: "Pretendard" };
  return s;
}

function rule(slide: any, x: number, y: number, w: number, color = C.line, h = 2) {
  slide.shapes.add({ geometry: "rect", position: { left: x, top: y, width: w, height: h }, fill: color,
    line: { style: "solid", fill: color, width: 0 } });
}

function title(slide: any, eyebrow: string, headline: string, page: number, dark = false) {
  text(slide, eyebrow, 82, 64, 700, 28, 16, dark ? C.lime : C.leaf, true);
  text(slide, headline, 80, 104, 1120, 72, 42, dark ? C.white : C.ink, true);
  text(slide, String(page).padStart(2, "0"), 1138, 674, 62, 20, 12, dark ? "#8FA595" : "#9AA49B", false, "right");
}

function brand(slide: any, dark = false) {
  box(slide, 81, 662, 22, 22, dark ? C.white : C.green, "rounded-md", dark ? C.white : C.green);
  text(slide, "팜", 82, 664, 20, 18, 10, dark ? C.green : C.white, true, "center");
  text(slide, "팜바톤 · FarmBaton", 112, 665, 230, 18, 12, dark ? "#8FA595" : "#8B958D");
}

function note(slide: any, lines: string[]) {
  slide.speakerNotes.textFrame.setText(lines);
  slide.speakerNotes.setVisible(true);
}

async function addImage(slide: any, file: string, x: number, y: number, w: number, h: number, fit: "cover" | "contain" = "cover", radius?: string) {
  const ext = path.extname(file).toLowerCase();
  slide.images.add({ blob: await bytes(file), contentType: ext === ".jpg" || ext === ".jpeg" ? "image/jpeg" : ext === ".svg" ? "image/svg+xml" : "image/png",
    alt: path.basename(file), fit, position: { left: x, top: y, width: w, height: h },
    ...(radius ? { geometry: "roundRect", borderRadius: radius } : {}) });
}

async function main() {
  await fs.mkdir(QA, { recursive: true });
  const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });

  // 1. Opening: image only.
  {
    const s = p.slides.add();
    await addImage(s, path.join(A, "apple_orchard_opening.png"), 0, 0, 1280, 720);
    note(s, ["이 사진이 무엇처럼 보이십니까? 사과농장입니다.", "이 농장을 다른 사람에게 그대로 넘기려면, 어디서부터 시작해야 할까요?", "[15초] 질문 뒤 1초간 멈춘다."]);
  }

  // 2. Fragmented succession.
  {
    const s = p.slides.add(); s.background.fill = C.ivory;
    title(s, "하나의 농장, 세 개의 처분", "농장은 하나지만, 승계 과정은 조각나 있습니다", 2);
    const cards = [
      ["orchard_land.png", "농지", "필지·면적·토지가격"],
      ["facility_machinery.png", "시설·기계", "창고·관수·농기계"],
      ["apples_market.png", "작목·판로", "수령·소득·거래관계"],
    ];
    for (let i=0;i<3;i++) { const x=80+i*384; box(s,x,218,352,344,C.white,"rounded-2xl"); await addImage(s,path.join(A,cards[i][0]),x+12,230,328,184,"cover","rounded-xl"); text(s,cards[i][1],x+22,432,200,34,26,C.green,true); text(s,cards[i][2],x+22,474,285,28,17,C.muted); }
    text(s,"농지, 시설, 기계를 전부 따로따로 처분해야 합니다",80,590,1120,42,26,C.leaf,true,"center"); brand(s);
    note(s,["상속지는 농지대로, 시설과 농기계는 별도로, 작목과 판로 정보는 다시 풀어야 합니다.","농장은 하나지만 승계 과정은 조각나 있습니다.","[25초]"]);
  }

  // 3. Teaser / reveal.
  {
    const s = p.slides.add(); s.background.fill=C.green;
    text(s,"농장 승계를",80,168,1120,70,38,C.darkPale,true);
    text(s,"조각이 아닌 하나의 흐름으로",80,244,1120,92,58,C.white,true);
    rule(s,80,392,1118,"#2C4736",2);
    text(s,"FarmBaton",80,426,700,82,62,C.lime,true);
    text(s,"농지 + 작목 + 시설 + 판로를 잇는 승계 진단·매칭 플랫폼",82,526,900,36,21,C.darkPale);
    brand(s,true); text(s,"03",1138,674,62,20,12,"#8FA595",false,"right");
    note(s,["[2초간 말없이 보여준다.]","이 조각들을 다시 하나로 잇는 서비스, 팜바톤입니다.","그렇다면 왜 지금 팜바톤이 필요할까요?", "[5초]"]);
  }

  // 4. Aging chart.
  {
    const s=p.slides.add(); s.background.fill=C.ivory; title(s,"문제의 크기", "농가 경영주는 늙고, 다음 주자는 줄고 있습니다",4);
    box(s,80,205,1120,390,C.white,"rounded-2xl");
    text(s,"(%)",116,226,40,20,12,C.muted);
    s.charts.add("line",{ position:{left:120,top:242,width:1040,height:300}, categories:["2005","2010","2015","2020","2025"],
      series:[{name:"40대 이하",values:[17.9,14.7,9.0,7.2,5.5],line:{style:"solid",fill:C.leaf,width:3}},{name:"60대 이상",values:[58.3,60.9,68.3,73.3,78.8],line:{style:"solid",fill:C.amber,width:3}}],
      hasLegend:true, legend:{position:"bottom"}, dataLabels:{showValue:true,position:"above"},
      yAxis:{minimumScale:0,maximumScale:90,majorUnit:10,majorGridlines:{style:"solid",fill:C.line,width:1}} });
    text(s,"출처: 통계청, 2025 농림어업총조사 결과(잠정)",82,612,650,24,13,"#8B958D"); brand(s);
    note(s,["통계청 2025 농림어업총조사 잠정 결과입니다.","60대 이상 경영주는 58.3%에서 78.8%로 높아졌고, 40대 이하는 17.9%에서 5.5%로 줄었습니다.","농장은 빠르게 늙지만 이어받을 사람은 줄고 있습니다.","[40초]"]);
  }

  // 5. Gap in alternatives.
  {
    const s=p.slides.add(); s.background.fill=C.ivory; title(s,"기존 대안의 공백","농장 전체를 진단하고 연결하는 통로가 비어 있습니다",5);
    const xs=[80,360,640,920], heads=["감정평가","부동산 중개","농지은행","팜바톤"], subs=["정확하지만 느리고 비쌈","토지 거래 중심","농지 중심 지원","농장 전체 + 매칭"];
    for(let i=0;i<4;i++){ const active=i===3; box(s,xs[i],232,240,284,active?C.pale:C.white,"rounded-2xl",active?C.leaf:C.line); text(s,heads[i],xs[i]+20,266,200,34,24,active?C.leaf:C.ink,true); rule(s,xs[i]+20,326,200,active?C.leaf:C.line,3); text(s,subs[i],xs[i]+20,358,198,80,18,C.muted); text(s,active?"농지·작목·시설·판로":"일부 요소만 해결",xs[i]+20,454,198,30,16,active?C.green:"#9AA49B",active); }
    text(s,"빠른 1차 검토에서 실제 상담까지, 하나의 흐름이 필요합니다",80,566,1120,38,25,C.green,true,"center"); brand(s);
    note(s,["기존 방법이 없는 것이 아닙니다. 다만 각각 농장의 일부만 봅니다.","농지는 물론 과수 수령, 시설, 판로까지 한 번에 진단하고 다음 주자와 연결하는 통로가 비어 있습니다.","[35초]"]);
  }

  // 6. Two MVP flows.
  {
    const s=p.slides.add(); s.background.fill=C.ivory; title(s,"팜바톤의 해법","두 개의 MVP 흐름에 집중했습니다",6);
    box(s,80,218,540,328,C.white,"rounded-2xl"); box(s,660,218,540,328,C.pale,"rounded-2xl",C.leaf);
    text(s,"01  농가 등록",112,252,430,30,18,C.leaf,true); text(s,"주소 하나로",112,304,430,48,34,C.green,true); text(s,"인수 검토 리포트",112,354,430,48,34,C.green,true);
    text(s,"농지 · 작목 · 시설 · 판로",112,432,420,28,17,C.muted); text(s,"→ 참고용 범위와 근거를 한눈에",112,472,430,30,17,C.leaf,true);
    text(s,"02  청년농 프로필",692,252,430,30,18,C.leaf,true); text(s,"희망 조건으로",692,304,430,48,34,C.green,true); text(s,"맞춤 농장 리스트",692,354,430,48,34,C.green,true);
    text(s,"지역 · 작목 · 자본 · 경험",692,432,420,28,17,C.muted); text(s,"→ 설명 가능한 매칭 점수",692,472,430,30,17,C.leaf,true); brand(s);
    note(s,["팜바톤은 두 가지 기능에 집중합니다.","농장주는 주소 하나로 인수 검토 리포트를 받고, 청년농은 희망 조건을 입력해 적합한 농장을 추천받습니다.","[25초]"]);
  }

  // 7. Demo cue.
  {
    const s=p.slides.add(); s.background.fill=C.ivory; title(s,"LIVE DEMO","등록 → 리포트 → 매칭, 3분 안에 보여드립니다",7);
    const files=["input.png","report.png","match.png"], labels=["1. 주소 입력","2. 인수 검토 리포트","3. 매칭 리스트"];
    for(let i=0;i<3;i++){ const x=78+i*395; box(s,x,220,360,330,C.white,"rounded-2xl"); await addImage(s,path.join(IMG,files[i]),x+12,232,336,236,"contain","rounded-xl"); text(s,labels[i],x+18,486,320,32,19,C.green,true,"center"); }
    text(s,"※ 데모 오류 시 동일 화면의 녹화 영상으로 즉시 전환",80,585,720,24,14,C.muted); brand(s);
    note(s,["[3분 라이브 데모]","0:00~0:50 농가 등록 / 0:50~1:40 인수 검토 리포트 / 1:40~2:30 청년농 매칭 / 2:30~3:00 상담 연결","결과 화면에서 반드시 ‘인수 검토가 범위(참고용 추정)’와 면책 문구를 짚는다."]);
  }

  // 8. Public data pipeline.
  {
    const s=p.slides.add(); s.background.fill=C.ivory; title(s,"공공데이터 활용","7종의 데이터를 하나의 의사결정 흐름으로 연결합니다",8);
    const nodes=[
      ["V-World","위치·공시지가"],["팜맵","필지·면적"],["실거래 DB","토지 보정"],["소득조사","작목 소득"],["KAMIS","시세 보정"],["기준표","시설·수령"],["중개업소","상담 연결"]
    ];
    for(let i=0;i<nodes.length;i++){ const x=80+(i%4)*280, y=218+Math.floor(i/4)*138; box(s,x,y,248,96,i===6?C.pale:C.white,"rounded-xl",i===6?C.leaf:C.line); text(s,nodes[i][0],x+16,y+18,216,28,19,i===6?C.leaf:C.green,true); text(s,nodes[i][1],x+16,y+52,216,22,14,C.muted); }
    box(s,922,356,278,96,C.green,"rounded-xl",C.green); text(s,"결정론적 산식",944,376,230,30,22,C.white,true,"center"); text(s,"인수 검토 범위 · 매칭",944,414,230,22,14,C.darkPale,false,"center");
    text(s,"하나라도 빠지면, 농장의 한 조각이 빠집니다",80,548,1120,38,25,C.green,true,"center"); brand(s);
    note(s,["팜바톤은 데이터를 단순히 나열하지 않습니다.","팜맵과 V-World, 실거래 DB, 농산물소득조사와 KAMIS, 기준표와 중개업소 정보를 가치평가와 연결의 흐름으로 묶습니다.","[50초]"]);
  }

  // 9. AI principle.
  {
    const s=p.slides.add(); s.background.fill=C.green; title(s,"AI 사용 원칙","숫자는 알고리즘, 설명은 AI",9,true);
    box(s,80,228,520,286,"#173924","rounded-2xl","#2C4736"); box(s,680,228,520,286,"#173924","rounded-2xl","#2C4736");
    text(s,"결정론적 Python 함수",112,266,440,34,24,C.lime,true); text(s,"가치평가 · 매칭 점수",112,322,440,42,31,C.white,true); text(s,"같은 입력 → 항상 같은 결과",112,402,440,28,18,C.darkPale);
    text(s,"생성형 AI",712,266,440,34,24,C.lime,true); text(s,"관점별 설명문",712,322,440,42,31,C.white,true); text(s,"계산 근거를 쉽게 풀어 전달",712,402,440,28,18,C.darkPale);
    rule(s,80,568,1120,"#2C4736",2); text(s,"LLM은 수치 계산에 사용하지 않습니다",80,590,1120,34,21,C.white,true,"center"); brand(s,true);
    note(s,["핵심은 AI를 어디에 쓰지 않았는가입니다.","금액과 매칭 점수는 결정론적 함수가 계산해 같은 입력에 같은 결과를 냅니다.","AI는 그 결과를 농장주와 청년농의 관점에 맞게 설명하는 역할만 합니다.","[40초]"]);
  }

  // 10. Architecture.
  {
    const s=p.slides.add(); s.background.fill=C.ivory; title(s,"기술성과 완성도","실제 배포를 전제로, 데모가 멈추지 않게 설계했습니다",10);
    const layers=[
      ["React · Vite · Leaflet","모바일 퍼스트 화면"],["FastAPI","검증된 가치평가·매칭 함수"],["PostgreSQL · PostGIS","공간 데이터 EPSG:4326"],["외부 API + 정적 폴백","V-World · KAMIS · 팜맵"]
    ];
    for(let i=0;i<4;i++){ const y=212+i*92; box(s,180,y,920,70,i===3?C.pale:C.white,"rounded-xl",i===3?C.leaf:C.line); text(s,layers[i][0],210,y+18,360,28,20,C.green,true); text(s,layers[i][1],600,y+20,450,26,16,C.muted); }
    text(s,"테스트 가능한 산식 · 공간데이터 통일 · 모든 외부 API의 정적 대체",80,600,1120,30,20,C.leaf,true,"center"); brand(s);
    note(s,["팜바톤은 화면 목업이 아니라 실제 배포 가능한 구조입니다.","공간 데이터는 PostGIS에 통일하고, 가치평가 산식은 테스트로 검증합니다.","외부 API마다 정적 폴백을 두어 데모가 멈추지 않도록 했습니다.","[35초]"]);
  }

  // 11. Differentiation.
  {
    const s=p.slides.add(); s.background.fill=C.ivory; title(s,"차별점","개별 기능보다, 농장 전체를 잇는 결합이 다릅니다",11);
    const ds=[["즉시","주소부터 시작"],["무료","첫 인수 검토"],["상속 기반 전체","농지+작목+시설+판로"],["현업 연결","공인중개 상담"]];
    for(let i=0;i<4;i++){ const x=80+i*280; box(s,x,236,252,292,i===2?C.pale:C.white,"rounded-2xl",i===2?C.leaf:C.line); text(s,String(i+1).padStart(2,"0"),x+20,260,50,26,15,C.leaf,true); text(s,ds[i][0],x+20,316,210,42,29,C.green,true); rule(s,x+20,378,210,i===2?C.leaf:C.line,3); text(s,ds[i][1],x+20,406,210,58,17,C.muted); }
    text(s,"확인한 범위에서: 빠른 검토 → 매칭 → 상담을 한 흐름으로",80,572,1120,34,23,C.green,true,"center"); brand(s);
    note(s,["차별점은 기술 하나가 아니라 결합에 있습니다.","농지뿐 아니라 수령, 시설, 영업권까지 반영하고, 그 결과를 청년농 매칭과 현업 상담으로 연결합니다.","[35초]"]);
  }

  // 12. Market & business.
  {
    const s=p.slides.add(); s.background.fill=C.ivory; title(s,"시장과 수익모델","3개 도·3개 과수에서 검증하고, B2G로 확장합니다",12);
    box(s,80,216,400,330,C.green,"rounded-2xl",C.green); text(s,"54.8만",112,266,330,76,58,C.lime,true); text(s,"70대 이상 농가 경영주",112,352,330,34,20,C.white,true); text(s,"출발 시장",112,420,330,26,15,C.darkPale);
    const items=[["초기 범위","충북 · 경북 · 충남\n사과 · 복숭아 · 포도"],["1차 수익","지자체 구독형 대시보드\n3개 도 × 48개 시군"],["확장 수익","제휴 공인중개업소\n상담 성공보수"]];
    for(let i=0;i<3;i++){ const y=216+i*110; box(s,520,y,680,92,C.white,"rounded-xl"); text(s,items[i][0],544,y+20,150,28,18,C.leaf,true); text(s,items[i][1],710,y+18,450,54,18,C.ink,true); }
    text(s,"개인 사용자는 계속 무료 → 농장 등록 장벽 최소화",520,572,680,30,20,C.green,true,"center"); brand(s);
    note(s,["출발 시장은 70대 이상 농가 경영주 54만 8천 가구입니다.","초기 범위는 충북·경북·충남의 사과·복숭아·포도 농가로 제한합니다.","수익은 지자체 구독형 대시보드에서 시작하고, 이후 제휴 공인중개업소의 상담 성공보수로 확장합니다.","[60초]"]);
  }

  // 13. Team.
  {
    const s=p.slides.add(); s.background.fill=C.ivory; title(s,"팀","기술·디자인·농업 현장을 한 팀에 담았습니다",13);
    const team=[["김정훈","개발 총괄","데이터 · 백엔드 · 배포"],["오채은","UI·UX","서비스 흐름 · 화면 설계"],["윤수민","농업 어드바이저","현장 검증 · 사용자 관점"]];
    for(let i=0;i<3;i++){ const x=80+i*384; box(s,x,238,352,282,C.white,"rounded-2xl"); box(s,x+24,264,64,64,i===0?C.green:C.pale,"rounded-full",i===0?C.green:C.leaf); text(s,team[i][0].slice(0,1),x+24,276,64,32,24,i===0?C.white:C.leaf,true,"center"); text(s,team[i][0],x+112,266,210,36,25,C.green,true); text(s,team[i][1],x+112,310,210,26,17,C.leaf,true); rule(s,x+24,360,304,C.line,2); text(s,team[i][2],x+24,390,304,54,17,C.muted); }
    text(s,"한 사람이 만든 기능이 아니라, 세 관점이 맞물린 서비스",80,570,1120,34,23,C.green,true,"center"); brand(s);
    note(s,["개발을 맡은 김정훈, UI·UX를 맡은 오채은, 농업 현장 검증을 맡은 윤수민으로 구성했습니다.","기술과 디자인, 농업 현장의 세 관점을 함께 갖춘 팀입니다.","[15초]"]);
  }

  // 14. Closing.
  {
    const s=p.slides.add(); await addImage(s,path.join(A,"apple_orchard_opening.png"),0,0,1280,720);
    s.shapes.add({geometry:"rect",position:{left:0,top:0,width:1280,height:720},fill:"#0E2518CC",line:{style:"solid",fill:"none",width:0}});
    text(s,"FarmBaton",80,116,700,66,26,C.lime,true); text(s,"농장은 처분하는 자산이 아니라",80,226,1040,58,38,C.white,true); text(s,"다음 농부에게 이어지는 삶의 기반입니다",80,292,1100,72,46,C.white,true);
    rule(s,80,414,1120,"#6F8B75",2); text(s,"인수 검토: 수일·수십만 원 → 무료·수십 초",80,446,1000,38,25,C.lime,true); text(s,"farmbaton.kr  ·  감사합니다",80,548,700,34,19,C.darkPale); brand(s,true); text(s,"14",1138,674,62,20,12,"#8FA595",false,"right");
    note(s,["처음 보여드린 사과농장은 낡은 자산이 아니라 다음 농부에게 이어갈 농장입니다.","인수 검토의 첫 문턱을 수일과 수십만 원에서 무료와 수십 초로 낮추겠습니다.","사라지는 농장의 데이터로 다음 농부를 잇겠습니다. 팜바톤이었습니다. 감사합니다.","[20초]"]);
  }

  // Render QA artifacts.
  for (const [i,s] of p.slides.items.entries()) {
    const stem=`slide-${String(i+1).padStart(2,"0")}`;
    const png=await p.export({slide:s,format:"png",scale:1});
    await fs.writeFile(path.join(QA,`${stem}.png`),new Uint8Array(await png.arrayBuffer()));
    const layout=await s.export({format:"layout"});
    await fs.writeFile(path.join(QA,`${stem}.layout.json`),await layout.text());
  }
  const montage=await p.export({format:"webp",montage:true,scale:1});
  await fs.writeFile(path.join(QA,"deck-montage.webp"),new Uint8Array(await montage.arrayBuffer()));
  const deck=await PresentationFile.exportPptx(p); await deck.save(OUT);
}

main().catch(e=>{ console.error(e); process.exitCode=1; });
