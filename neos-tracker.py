import streamlit as st
import pandas as pd
import yfinance as yf
import re, time, os
from datetime import datetime

st.set_page_config(page_title="NEOS Monitor", layout="wide")
st.title("🛡️ NEOS ETF Options Portfolio Dashboard")
loop = st.sidebar.checkbox("Auto-Refresh Tickers (10s)", value=True)

TICKERS = {
    "SPYI": ("^SPX", "S&P 500® High Income ETF"), 
    "QQQI": ("^NDX", "Nasdaq-100® High Income ETF"),
    "IWMI": ("^RUT", "Russell 2000® High Income ETF"), 
    "NIHI": ("EFA", "MSCI EAFE High Income ETF"),
    "XSPI": ("^SPX", "Boosted S&P 500® High Income ETF"), 
    "XQQI": ("^NDX", "Boosted Nasdaq-100® High Income ETF"),
    "XBCI": ("^CBTX", "Boosted Bitcoin High Income ETF"), 
    "BTCI": ("^CBTX", "Bitcoin High Income ETF"),
    "NEHI": ("BIL", "Ethereum High Income ETF"), 
    "IYRI": ("IYR", "Real Estate High income ETF"),
    "IAUI": ("GLD", "Gold High Income ETF"), 
    "MLPI": ("AMLP", "MLP & Energy Infrastructure High Income ETF"),
    "QQQH": ("^NDX", "Nasdaq-100® Hedged Equity Income ETF"), 
    "SPYH": ("^SPX", "S&P 500® Hedged Equity Income ETF"),
    "NLSI": ("^NDX", "Long/Short Equity Income ETF"), 
    "CSHI": ("^SPX", "Enhanced Income 1-3 Month T-Bill ETF"),
    "TLTI": ("^SPX", "Enhanced Income 20+ Year Treasury Bond ETF"), 
    "BNDI": ("^SPX", "Enhanced Income Aggregate Bond ETF"),
    "HYBI": ("^SPX", "Enhanced Income Credit Select ETF")
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
    if not any(k in ln for k in ["SPX", "NDX", "RUT", "MXEA", "CBTX", "BIL", "IYR", "GLD", "AMLP"]): return None
    is_c = "CALL" in ln or " C " in ln or " C," in ln or ",C," in ln or "C26" in ln or "C25" in ln
    is_p = "PUT" in ln or " P " in ln or " P," in ln or ",P," in ln or "P26" in ln or "P25" in ln
    m_occ = re.search(r'([A-Z0-9]+)\s*(\d{6})([CP])(\d{8})', ln)
    if m_occ:
        sym, date_str, opt_char, raw_strike_str = m_occ.groups()
        opt_type = 'C' if opt_char == 'C' else 'P'
        dte = None
        try: dte = (datetime.strptime(date_str, "%y%m%d").date() - datetime.today().date()).days
        except: pass
        strike_val = float(raw_strike_str)
        #if "CBTX" in sym: return opt_type, strike_val / 10000.0, dte
        #el
        if "BIL" in sym or "NEHI" in ln: return opt_type, strike_val / 100000.0, dte
        return opt_type, strike_val / 1000.0, dte
    return None

def analyze_local_file(filepath, hedged=True, is_fixed_income=False):
    if not os.path.exists(filepath): return None, f"Missing: `{os.path.basename(filepath)}`"
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f: lines = f.read().splitlines()
        raw_legs, total_v, dte_l = [], 0.0, []
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
                is_short = "-" in l or "SHORT" in l.upper()
                raw_legs.append({'t': t, 'st': strike, 'sh': is_short, 'cv': 0.5})

        filtered_legs = []
        for leg in raw_legs:
            is_synthetic = False
            if "CBTX" in filepath or "BTC" in filepath:
                for mirror in raw_legs:
                    if leg['st'] == mirror['st'] and leg['t'] != mirror['t']:
                        is_synthetic = True
                        break
            if not is_synthetic: filtered_legs.append(leg)

        calls = [l for l in filtered_legs if l['t'] == 'C']
        puts = [l for l in filtered_legs if l['t'] == 'P']
        if not calls and not puts: return None, "No active income overlay options found."
        avg_dte = round(sum(dte_l)/len(dte_l)) if dte_l else "N/A"

        if is_fixed_income:
            all_opts = puts if puts else calls
            s_legs = [o['st'] for o in all_opts]
            sp_floor = min(s_legs) if len(s_legs) >= 2 else s_legs - 50
            lp_threshold = max(s_legs) if len(s_legs) >= 2 else s_legs
            return {"c1": lp_threshold+50, "c2": lp_threshold+50, "lp": lp_threshold, "sp": sp_floor, "dte": avg_dte, "cp1": 0, "cp2": 0, "multi": False, "spread": True}, None

        if not calls: return None, "Missing written income call options."
        s_c = sorted([c for c in calls if c['sh']], key=lambda x: x['st']) # Fixed variable index typing mismatch
        if not s_c: s_c = sorted(calls, key=lambda x: x['st'])
        c1_obj = s_c[0]
        c2_obj = s_c[-1] if len(s_c) > 1 else s_c[0]
        
        if not hedged or not puts:
            return {"c1": c1_obj['st'], "c2": c2_obj['st'], "lp": c1_obj['st'], "sp": c1_obj['st'], "dte": avg_dte, "cp1": 0, "cp2": 0, "multi": len(s_c) > 1, "spread": False}, None
            
        all_p = sorted(list(set([p['st'] for p in puts])), reverse=True)
        lp = all_p[0] if all_p else c1_obj['st']
        sp = all_p[-1] if len(all_p) >= 2 else (all_p[0] if all_p else c1_obj['st'])
        return {"c1": c1_obj['st'], "c2": c2_obj['st'], "lp": lp, "sp": sp, "dte": avg_dte, "cp1": 0, "cp2": 0, "multi": len(s_c) > 1, "spread": False}, None
    except Exception as e: return None, f"File Error: {str(e)}"

def draw_bar(val, sp, lp, c1, c2, cp1, cp2, hedged=True, multi=False, spread=False):
    if not val: return "<p style='color:gray;'>Awaiting price data...</p>"
    w, by, bh = 800, 60, 40
    def col(p): return "#40A060" if p > 0 else ("#E05252" if p < 0 else "gray")
    def sgn(p): return "+" if p > 0 else ""
    if spread:
        min_v, max_v = sp * 0.95, lp * 1.05
        r = max_v - min_v if max_v != min_v else 1.0
        def gx_sp(v): return max(0.02, min(0.98, (v - min_v) / r)) * w
        x_sp, x_lp, x_live = gx_sp(sp), gx_sp(lp), gx_sp(val)
        lp_p, sp_p = ((lp - val) / val) * 100, ((sp - val) / val) * 100
        return f"""<svg width="100%" height="150" viewBox="0 0 {w} 150" xmlns="http://w3.org">
        <style>.l-b {{font:bold 13px sans-serif; fill:currentColor;}} .l-s {{font:bold 11px sans-serif; fill:#FFF;}} .l-d {{font:bold 11px sans-serif; fill:#1E1E1E;}} .p-t {{font:bold 14px sans-serif; fill:currentColor;}} .pct-lbl {{font:bold 12px sans-serif;}}</style>
        <rect x="0" y="{by}" width="{x_sp}" height="{bh}" fill="#E05252" stroke="currentColor" stroke-width="1.5"/><text x="{x_sp/2}" y="{by+24}" text-anchor="middle" class="l-s">Loss Exposure</text>
        <rect x="{x_sp}" y="{by}" width="{x_lp-x_sp}" height="{bh}" fill="#F4C430" stroke="currentColor" stroke-width="1.5"/><text x="{x_sp+(x_lp-x_sp)/2}" y="{by+24}" text-anchor="middle" class="l-d">Spread Range Buffer</text>
        <rect x="{x_lp}" y="{by}" width="{w-x_lp}" height="{bh}" fill="#40A060" stroke="currentColor" stroke-width="1.5"/><text x="{x_lp+(w-x_lp)/2}" y="{by+24}" text-anchor="middle" class="l-s">Maximum Yield Capture</text>
        <text x="{x_sp}" y="{by+bh+18}" text-anchor="middle" class="l-b">{sp:,.0f}</text><text x="{x_lp}" y="{by+bh+18}" text-anchor="middle" class="l-b">{lp:,.0f}</text>
        <text x="{x_sp}" y="{by+bh+34}" text-anchor="middle" class="pct-lbl" fill="{col(sp_p)}">{sgn(sp_p)}{sp_p:.2f}%</text><text x="{x_lp}" y="{by+bh+34}" text-anchor="middle" class="pct-lbl" fill="{col(lp_p)}">{sgn(lp_p)}{lp_p:.2f}%</text>
        <g transform="translate({x_live}, 0)"><text x="0" y="24" text-anchor="middle" class="p-t">{val:,.2f}</text><path d="M 0,52 L -8,38 L 8,38 Z" fill="currentColor" stroke="currentColor"/><line x1="0" y1="38" x2="0" y2="{by+bh}" stroke="currentColor" stroke-dasharray="3,3" stroke-width="1.5"/></g></svg>"""
    if not hedged or sp == lp or sp == c1:
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
p_ndx, p_spx = get_price("^NDX"), get_price("^SPX")

for cat_name, symbols in CATEGORIES.items():
    st.markdown(f"---")
    st.subheader(f"💼 {cat_name}")
    cols = st.columns(2)
    for index, sym in enumerate(symbols):
        target_col = cols[index % 2]
        with target_col:
            yf_ticker, description = TICKERS.get(sym, ("^SPX", "S&P 500"))

            st.markdown(f"### 📈 {sym} - {description}")

            live_price = get_price(yf_ticker)
            if live_price and sym == "NIHI": live_price *= 30.0
            #if live_price and sym in ["XBCI", "BTCI"]: live_price /= 10.0
            if live_price: st.metric(f"Live Base Value ({yf_ticker})", f"{live_price:,.2f}")
            else: st.warning("⚠️ Live market polling offline.")
            file_path = os.path.join(base_dir, f"NEOS Holdings - {sym} Holdings.csv")
            is_hedged_cat = (cat_name == "Hedged Equity Income")
            is_fixed_inc_cat = (cat_name == "Enhanced Fixed Income")
            
            d, err = analyze_local_file(file_path, hedged=is_hedged_cat, is_fixed_income=is_fixed_inc_cat)
            if err: st.error(err)
            elif d:
                f_sp = d.get("sp")
                f_lp = d.get("lp")
                f_spread = d.get("spread", False)
                st.write(draw_bar(live_price, f_sp, f_lp, d["c1"], d["c2"], d["cp1"], d["cp2"], hedged=is_hedged_cat, multi=d.get("multi", False), spread=f_spread), unsafe_allow_html=True)

                
                
                st.caption(f"🛡️ Strategy Pattern: **{cat_name} Matrix** | ⏱️ **{d['dte']} Days to Expiration**")

if loop: time.sleep(10); st.rerun()
	
