import streamlit as st
import pandas as pd
import yfinance as yf
import re, time, os
from datetime import datetime

st.set_page_config(page_title="NEOS Matrix Tracker", layout="wide")
st.title("🛡️ NEOS ETF Options Portfolio Dashboard")
loop = st.sidebar.checkbox("Auto-Refresh Tickers (10s)", value=True)

# Central asset map containing live Yahoo Finance data endpoints
TICKERS = {
    "SPYI": ("^SPX", "S&P 500"), "QQQI": ("^NDX", "Nasdaq-100"),
    "IWMI": ("^RUT", "Russell 2000"), "NIHI": ("^SPX", "Nikkei 225"),
    "XSPI": ("^SPX", "Boosted S&P 500"), "XQQI": ("^NDX", "Boosted Nasdaq"),
    "XBCI": ("^SPX", "Boosted Bitcoin Proxy"), "BTCI": ("^SPX", "Bitcoin Options"),
    "NEHI": ("^SPX", "High Income Alternate"), "IYRI": ("^DJR", "Dow Jones Real Estate"),
    "IAUI": ("GC=F", "Gold Bullion Options"), "MLPI": ("^AMZ", "MLP Infrastructure"),
    "QQQH": ("^NDX", "Hedged Nasdaq"), "SPYH": ("^SPX", "Hedged S&P 500"),
    "NLSI": ("^NDX", "Hedged Large Cap"), "CSHI": ("^SPX", "Cash Income Proxy"),
    "TLTI": ("^TYX", "Treasury Bond Options"), "BNDI": ("^SPX", "Total Bond Options"),
    "HYBI": ("^SPX", "High Yield Options Layer")
}

CATEGORIES = {
    "Equity High Income": ["SPYI", "QQQI", "IWMI", "NIHI"],
    "Boosted High Income": ["XSPI", "XQQI", "XBCI"],
    "High Income Alternatives": ["BTCI", "NEHI", "IYRI", "IAUI", "MLPI"],
    "Hedged Equity Income": ["QQQH", "SPYH", "NLSI"],
    "Enhanced Fixed Income": ["CSHI", "TLTI", "BNDI", "HYBI"]
}

@st.cache_data(ttl=10)
def get_price(sym):
    try:
        df = yf.Ticker(sym).history(period="1d")
        if not df.empty: return df['Close'].iloc[-1]
    except: pass
    return None

def parse_opt(txt):
    ln = str(txt).upper().replace('"', '').replace("'", "")
    # Recognize index root benchmarks universally
    if not any(k in ln for k in ["SPX", "NDX", "RUT", "NIK", "BTC", "GOLD", "US10", "BND"]):
        # Universal fallback pass if the symbol matches common clearing codes
        if not any(k in ln for k in [" C", " P", "CALL", "PUT"]): return None
    is_c = "CALL" in ln or " C " in ln or " C," in ln or ",C," in ln
    is_p = "PUT" in ln or " P " in ln or " P," in ln or ",P," in ln
    if not is_c and not is_p:
        if re.search(r'C\d{7,8}', ln): is_c = True
        elif re.search(r'P\d{7,8}', ln): is_p = True
    if not (is_c or is_p): return None
    
    t, dte = 'C' if is_c else 'P', None
    m_d = re.search(r'\s*(\d{6})([CP])', ln)
    if m_d:
        try: dte = (datetime.strptime(m_d.group(1), "%y%m%d").date() - datetime.today().date()).days
        except: pass
    m_o = re.search(r'([CP])\s*(\d{8})', ln)
    if m_o: return t, float(m_o.group(2)) / 1000, dte
    nums = re.findall(r'\b\d+(?:\.\d+)?\b', ln)
    for n in nums:
        v = float(n)
        if v > 100000: v /= 1000
        if 50 <= v <= 35000: return t, v, dte
    return None

def analyze_local_file(filepath, hedged=True):
    if not os.path.exists(filepath): return None, f"Missing local cache file footprint: `{os.path.basename(filepath)}`"
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f: lines = f.read().splitlines()
        calls, puts, dte_l, total_v = [], [], [], 0.0
        for l in lines:
            if any(x in l.upper() for x in ["<P", "<DIV", "STYLE=", "TOTAL"]): continue
            els = l.split(',')
            if len(els) >= 4:
                try:
                    v_s = els[-1].replace('"','').replace('$','').replace(',','').strip()
                    if v_s and not any(c.isalpha() for c in v_s): total_v += float(v_s)
                except: pass
        if total_v < 1000000: total_v = 50000000.0
        for l in lines:
            if any(x in l.upper() for x in ["<P", "<DIV", "STYLE=", "30-DAY SEC", "DISCLOSURE"]): continue
            p = parse_opt(l)
            if p:
                t, strike, dte = p
                if dte is not None: dte_l.append(dte)
                els = l.split(',')
                sh = 0.0
                for e in els:
                    e_s = e.replace('"','').replace(',','').strip()
                    if e_s.startswith('-') or (e_s.isdigit() and '.' in e_s) or e_s.isnumeric():
                        try: sh = float(e_s); break
                        except: pass
                cov = min(1.0, (abs(sh) * 100.0 * strike) / total_v) if total_v > 0 else 1.0
                if t == 'C': calls.append({'st': strike, 'sh': sh < 0, 'cv': cov})
                else: puts.append({'st': strike, 'sh': sh < 0, 'cv': cov})
        if not calls: return None, "No option assets found inside file structure mapping profiles."
        s_c = sorted([c for c in calls if c['sh']], key=lambda x: x['st'])
        if not s_c: s_c = sorted(calls, key=lambda x: x['st'])
        c1_obj, c2_obj = s_c[0], (s_c[-1] if len(s_c) > 1 else s_c[0])
        c1_pt = round((1.0 - c1_obj['cv']) * 100)
        c2_pt = round(max(0, (1.0 - (c1_obj['cv'] + c2_obj['cv']))) * 100) if len(s_c) > 1 else c1_pt
        avg_dte = round(sum(dte_l)/len(dte_l)) if dte_l else "N/A"
        if not hedged or not puts: return {"c1": c1_obj['st'], "c2": c2_obj['st'], "dte": avg_dte, "cp1": c1_pt, "cp2": c2_pt, "multi": len(s_c) > 1}, None
        l_p = [p for p in puts if not p['sh']]
        s_p = [p for p in puts if p['sh']]
        lp = max([p['st'] for p in l_p]) if l_p else sorted(list(set([p['st'] for p in puts])), reverse=True)[0]
        sp = min([p['st'] for p in s_p]) if s_p else sorted(list(set([p['st'] for p in puts])), reverse=True)[-1]
        return {"c1": c1_obj['st'], "c2": c2_obj['st'], "lp": lp, "sp": sp, "dte": avg_dte, "cp1": c1_pt, "cp2": c2_pt, "multi": len(s_c) > 1}, None
    except Exception as e: return None, f"File Error: {str(e)}"
		
def draw_bar(val, sp, lp, c1, c2, cp1, cp2, hedged=True, multi=False):
    if not val: return "<p style='color:gray;'>Awaiting price parameters...</p>"
    w, by, bh = 800, 60, 40
    def col(p): return "#40A060" if p > 0 else ("#E05252" if p < 0 else "gray")
    def sgn(p): return "+" if p > 0 else ""
    
    if not hedged or sp is None:
        min_v, max_v = c1 * 0.90, c2 * 1.10
        r = max_v - min_v if max_v != min_v else 1.0
        def gx2(v): return max(0.02, min(0.98, (v - min_v) / r)) * w
        x_c1, x_c2, x_live = gx2(c1), gx2(c2), gx2(val)
        u1, u2 = ((c1 - val) / val) * 100, ((c2 - val) / val) * 100
        cap_txt = "No Participation" if cp1 == 0 else f"{cp1}% Participation"
        
        if multi:
            return f"""<svg width="100%" height="150" viewBox="0 0 {w} 150" xmlns="http://w3.org">
            <style>.l-b {{font:bold 13px sans-serif; fill:currentColor;}} .l-s {{font:bold 11px sans-serif; fill:#FFF;}} .l-d {{font:bold 11px sans-serif; fill:#1E1E1E;}} .p-t {{font:bold 14px sans-serif; fill:currentColor;}} .pct-lbl {{font:bold 12px sans-serif;}}</style>
            <rect x="0" y="{by}" width="{x_c1}" height="{bh}" fill="#40A060" stroke="currentColor" stroke-width="1.5"/><text x="{x_c1/2}" y="{by+24}" text-anchor="middle" class="l-s">Full Participation</text>
            <rect x="{x_c1}" y="{by}" width="{x_c2-x_c1}" height="{bh}" fill="#F4C430" stroke="currentColor" stroke-width="1.5"/><text x="{x_c1+(x_c2-x_c1)/2}" y="{by+24}" text-anchor="middle" class="l-d">{cp1}% Participation</text>
            <rect x="{x_c2}" y="{by}" width="{w-x_c2}" height="{bh}" fill="#E05252" stroke="currentColor" stroke-width="1.5"/><text x="{x_c2+(w-x_c2)/2}" y="{by+24}" text-anchor="middle" class="l-s">{"No Participation" if cp2==0 else f"{cp2}% Participation"}</text>
            <text x="{x_c1}" y="{by+bh+18}" text-anchor="middle" class="l-b">{c1:,.0f}</text><text x="{x_c2}" y="{by+bh+18}" text-anchor="middle" class="l-b">{c2:,.0f}</text>
            <text x="{x_c1}" y="{by+bh+34}" text-anchor="middle" class="pct-lbl" fill="{col(u1)}">{sgn(u1)}{u1:.2f}%</text><text x="{x_c2}" y="{by+bh+34}" text-anchor="middle" class="pct-lbl" fill="{col(u2)}">{sgn(u2)}{u2:.2f}%</text>
            <g transform="translate({x_live}, 0)"><text x="0" y="24" text-anchor="middle" class="p-t">{val:,.2f}</text><path d="M 0,52 L -8,38 L 8,38 Z" fill="currentColor" stroke="currentColor"/><line x1="0" y1="38" x2="0" y2="{by+bh}" stroke="currentColor" stroke-dasharray="3,3" stroke-width="1.5"/></g></svg>"""
        return f"""<svg width="100%" height="150" viewBox="0 0 {w} 150" xmlns="http://w3.org">
        <style>.l-b {{font:bold 13px sans-serif; fill:currentColor;}} .l-s {{font:bold 11px sans-serif; fill:#FFF;}} .p-t {{font:bold 14px sans-serif; fill:currentColor;}} .pct-lbl {{font:bold 12px sans-serif;}}</style>
        <rect x="0" y="{by}" width="{x_c1}" height="{bh}" fill="#40A060" stroke="currentColor" stroke-width="1.5"/><text x="{x_c1/2}" y="{by+24}" text-anchor="middle" class="l-s">Full Participation</text>
        <rect x="{x_c1}" y="{by}" width="{w-x_c1}" height="{bh}" fill="#E05252" stroke="currentColor" stroke-width="1.5"/><text x="{x_c1+(w-x_c1)/2}" y="{by+24}" text-anchor="middle" class="l-s">{cap_txt}</text>
        <text x="{x_c1}" y="{by+bh+18}" text-anchor="middle" class="l-b">{c1:,.0f}</text><text x="{x_c1}" y="{by+bh+34}" text-anchor="middle" class="pct-lbl" fill="{col(u1)}">{sgn(u1)}{u1:.2f}%</text>
        <g transform="translate({x_live}, 0)"><text x="0" y="24" text-anchor="middle" class="p-t">{val:,.2f}</text><path d="M 0,52 L -8,38 L 8,38 Z" fill="currentColor" stroke="currentColor"/><line x1="0" y1="38" x2="0" y2="{by+bh}" stroke="currentColor" stroke-dasharray="3,3" stroke-width="1.5"/></g></svg>"""

    r = (c1 * 1.10) - (sp * 0.90) if (c1 * 1.10) != (sp * 0.90) else 1.0
    def gx(v): return max(0.02, min(0.98, (v - (sp * 0.90)) / r)) * w
    x_sp, x_lp, x_c1, x_live = gx(sp), gx(lp), gx(c1), gx(val)
    u1, lp_p, sp_p = ((c1 - val) / val) * 100, ((lp - val) / val) * 100, ((sp - val) / val) * 100
    cap_txt = "No Participation" if cp1 == 0 else f"{cp1}% Participation"
    return f"""<svg width="100%" height="150" viewBox="0 0 {w} 150" xmlns="http://w3.org">
    <style>.l-b {{font:bold 13px sans-serif; fill:currentColor;}} .l-s {{font:bold 11px sans-serif; fill:#FFF;}} .l-d {{font:bold 11px sans-serif; fill:#1E1E1E;}} .p-t {{font:bold 14px sans-serif; fill:currentColor;}} .pct-lbl {{font:bold 12px sans-serif;}}</style>
    <rect x="0" y="{by}" width="{x_sp}" height="{bh}" fill="#E05252" stroke="currentColor" stroke-width="1.5"/><text x="{x_sp/2}" y="{by+24}" text-anchor="middle" class="l-s">No Loss Protection</text>
    <rect x="{x_sp}" y="{by}" width="{x_lp-x_sp}" height="{bh}" fill="#F4C430" stroke="currentColor" stroke-width="1.5"/><text x="{x_sp+(x_lp-x_sp)/2}" y="{by+24}" text-anchor="middle" class="l-d">Protection Active</text>
    <rect x="{x_lp}" y="{by}" width="{x_c1-x_lp}" height="{bh}" fill="#40A060" stroke="currentColor" stroke-width="1.5"/><text x="{x_lp+(x_c1-x_lp)/2}" y="{by+24}" text-anchor="middle" class="l-s">Full Participation</text>
    <rect x="{x_c1}" y="{by}" width="{w-x_c1}" height="{bh}" fill="#E05252" stroke="currentColor" stroke-width="1.5"/><text x="{x_c1+(w-x_c1)/2}" y="{by+24}" text-anchor="middle" class="l-s">{cap_txt}</text>
    <text x="{x_sp}" y="{by+bh+18}" text-anchor="middle" class="l-b">{sp:,.0f}</text><text x="{x_lp}" y="{by+bh+18}" text-anchor="middle" class="l-b">{lp:,.0f}</text><text x="{x_c1}" y="{by+bh+18}" text-anchor="middle" class="l-b">{c1:,.0f}</text>
    <text x="{x_sp}" y="{by+bh+34}" text-anchor="middle" class="pct-lbl" fill="{col(sp_p)}">{sgn(sp_p)}{sp_p:.2f}%</text><text x="{x_lp}" y="{by+bh+34}" text-anchor="middle" class="pct-lbl" fill="{col(lp_p)}">{sgn(lp_p)}{lp_p:.2f}%</text><text x="{x_c1}" y="{by+bh+34}" text-anchor="middle" class="pct-lbl" fill="{col(u1)}">{sgn(u1)}{u1:.2f}%</text>
    <g transform="translate({x_live}, 0)"><text x="0" y="24" text-anchor="middle" class="p-t">{val:,.2f}</text><path d="M 0,52 L -8,38 L 8,38 Z" fill="currentColor" stroke="currentColor"/><line x1="0" y1="38" x2="0" y2="{by+bh}" stroke="currentColor" stroke-dasharray="3,3" stroke-width="1.5"/></g></svg>"""

base_dir = os.path.dirname(os.path.abspath(__file__))

# Single unified render pass iterating through all system categories
for cat_name, symbols in CATEGORIES.items():
    st.markdown(f"---")
    st.subheader(f"💼 {cat_name}")
    
    # Establish responsive dual columns per sector block layout row
    cols = st.columns(2)
    for index, sym in enumerate(symbols):
        target_col = cols[index % 2]
        
        with target_col:
            st.markdown(f"### 📈 {sym} Options Tracker")
            
            # Map ticker asset underlying targets
            yf_ticker, description = TICKERS.get(sym, ("^SPX", "S&P 500"))
            live_price = get_price(yf_ticker)
            
            if live_price:
                st.metric(f"Live {sym} Base Value ({description})", f"{live_price:,.2f}")
            else:
                st.warning("⚠️ Live market polling offline.")
                
            # Direct loading check using identical naming standards
            file_name = f"NEOS Holdings - {sym} Holdings.csv"
            file_path = os.path.join(base_dir, file_name)
            
            is_hedged_cat = (cat_name == "Hedged Equity Income")
            d, err = analyze_local_file(file_path, hedged=is_hedged_cat)
            
            if err:
                st.error(err)
            elif d:
                # Direct conditional parameters handoff to drawing engine
                f_sp = d.get("sp") if is_hedged_cat else None
                f_lp = d.get("lp") if is_hedged_cat else None
                f_multi = d.get("multi", False)
                
                st.write(draw_bar(live_price, f_sp, f_lp, d["c1"], d["c2"], d["cp1"], d["cp2"], hedged=is_hedged_cat, multi=f_multi), unsafe_allow_html=True)
                st.caption(f"⏱️ Option Expiration Tracking Profile: **{d['dte']} Days to Expiration**")

# Background thread looping trigger
if loop:
    time.sleep(10)
    st.rerun()
