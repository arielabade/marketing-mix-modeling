"""Client report page: ``docs/dashboard/``, served by GitHub Pages.

Same contract as the unit-economics-olist dashboard:

* **Python (this module)** decides *what is said*: every sentence, number and
  action title of the page, computed from the job outputs (with a neutral
  fallback when the claim does not hold), and every table, so the page is
  complete and readable without JavaScript. Chart data goes in one JSON block.
* **assets/** holds *how it looks and behaves*: ``index.html`` (structure with
  ``[[slot]]`` placeholders), ``styles.css`` (ABADE tokens, light/dark, print)
  and ``app.js`` (charts drawn lazily from the JSON in the active theme, the
  state map, theme switch, section highlight).
* **vendor/** ships plotly.js (cartesian bundle, pinned): no CDN, no server.

Storytelling rules come from ``arielabade/prompts`` (dashboard/ and
agentes-dados/): conclusion in every title, context before numbers, grey plus
the two protagonists (Meta in cobalt, TikTok in orange), table twin for every
chart, method folded away.

Input: the dict built by ``mmm.jobs.report.build_data``. Output: the files of
``docs/dashboard``. Dependencies: pandas, numpy (formatting only).
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
from pathlib import Path

import numpy as np

from ..settings import ROOT

ASSETS = Path(__file__).resolve().parent / "assets"
PLOTLY = ROOT / "vendor" / "plotly-cartesian-4.1.1.min.js"
SYMBOL_VIEWBOX = "0 0 127.566 100"
NBSP, MINUS = " ", "−"
LABELS = {"meta": "Meta Ads", "tiktok": "TikTok Ads", "google_search": "Google Busca",
          "google_shopping": "Google Shopping/PMax", "youtube": "YouTube", "afiliados": "Afiliados"}
VERDICTS = {"channel_is_incremental": "a Meta gera receita incremental", "real_but_small": "efeito real, mas pequeno",
            "inconclusive": "inconclusivo", "no_effect": "sem efeito detectável"}


# --- formatting (pt-BR) -------------------------------------------------------------

def _na(v) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v))


def _num(v: float, digits: int = 0) -> str:
    return f"{v:,.{digits}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def brl(v, digits: int = 0) -> str:
    if _na(v):
        return "—"
    return f"{MINUS if v < 0 else ''}R${NBSP}{_num(abs(v), digits)}"


def brl_short(v) -> str:
    if _na(v):
        return "—"
    s, a = (MINUS if v < 0 else ""), abs(v)
    if a >= 1e6:
        return f"{s}R${NBSP}{_num(a / 1e6, 2)}{NBSP}mi"
    if a >= 1e3:
        return f"{s}R${NBSP}{_num(a / 1e3, 1 if a < 1e4 else 0)}{NBSP}mil"
    return brl(v)


def pct(v, digits: int = 0, signed: bool = False) -> str:
    if _na(v):
        return "—"
    shown = round(v * 100, digits)
    if shown == 0:
        return "0%"
    text = _num(abs(shown), digits)
    text = (text[:-2] if text.endswith(",0") else text) + "%"  # "12%", not "12,0%"
    return (MINUS + text) if shown < 0 else ("+" + text if signed else text)


def per_real(v) -> str:
    """Return per R$ 1 spent, as a client reads it: "R$ 1,97"."""
    return brl(v, 2)


def esc(text) -> str:
    return html.escape(str(text))


def label(c: str) -> str:
    return LABELS.get(c, c)


def name(c: str) -> str:
    """Channel name, coloured when it is one of the two protagonists."""
    cls = {"meta": "name-meta", "tiktok": "name-tiktok"}.get(c)
    return f'<span class="{cls}">{esc(label(c))}</span>' if cls else esc(label(c))


def listing(items: list[str]) -> str:
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " e " + items[-1] if items else ""


def nbsp(text: str) -> str:
    text = re.sub(r"R\$ (?=[−\d])", "R$" + NBSP, text)
    return re.sub(r"(?<=\d) (mi|mil)\b", NBSP + r"\1", text)


def date_br(iso: str) -> str:
    y, m, d = str(iso)[:10].split("-")
    return f"{d}/{m}/{y}"


MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
          "novembro", "dezembro"]


def month_long(iso: str) -> str:
    y, m = str(iso)[:7].split("-")
    return f"{MONTHS[int(m) - 1]} de {y}"


# --- tables (server-rendered: the page works without JavaScript) --------------------

def table(caption: str, columns: list[str], rows: list[list[str]], numeric_from: int = 1) -> str:
    num = ' class="num"'
    head = "".join(f'<th scope="col"{num if i >= numeric_from else ""}>{esc(c)}</th>' for i, c in enumerate(columns))
    body = "".join("<tr>" + "".join(
        (f'<th scope="row">{v}</th>' if i == 0 else f'<td class="num">{v}</td>' if i >= numeric_from else f"<td>{v}</td>")
        for i, v in enumerate(r)) + "</tr>" for r in rows)
    return (f'<div class="table-wrap" tabindex="0"><table class="data compact"><caption>{esc(caption)}</caption>'
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


# --- the story ------------------------------------------------------------------------

def _roi(d: dict, kind: str) -> dict:
    return {r["channel"]: r for r in (d.get("roi") or {}).get(kind, [])}


def _allocation(d: dict) -> tuple[str | None, dict | None]:
    a = d.get("allocation") or {}
    for k in ("calibrated", "uncalibrated"):
        if a.get(k):
            return k, a[k]
    return None, None


def _moves(a: dict) -> list[dict]:
    rows = []
    for c in a["channels"]:
        cur = c["current_daily_at_budget"] * a["horizon_days"]
        rows.append({**c, "current_total": cur, "delta": c["recommended_total"] - cur})
    return rows


def story(d: dict) -> dict[str, str]:
    """Every computed sentence of the page. Each claim checks its own condition."""
    s: dict[str, str] = {}
    kind, a = _allocation(d)
    u, c = _roi(d, "uncalibrated"), _roi(d, "calibrated")
    main = c or u
    g = d.get("geolift") or {}
    sp = d.get("spend") or {}
    ev = (d.get("evaluation") or {}).get("roi_recovery") or {}
    truth = {r["channel"]: r for r in d.get("roi_vs_truth") or []}

    # hero + summary
    ups = downs = []
    if a:
        mv = _moves(a)
        ups = [m["channel"] for m in sorted(mv, key=lambda m: -m["delta"]) if m["change_pct"] > 0.02]
        downs = [m["channel"] for m in sorted(mv, key=lambda m: m["delta"]) if m["change_pct"] < -0.02]
    confident = bool(a and a["gain_mean"] > 0 and a["prob_better"] >= 0.8)
    if confident and ups and downs:
        s["h1"] = (f"A mesma verba rende {brl_short(a['gain_mean'])} a mais por mês com mais {label(ups[0])} "
                   f"e menos {label(downs[0])}")
    elif a:
        s["h1"] = "A divisão atual da verba está perto do ponto ótimo"
    else:
        s["h1"] = "Onde investir o próximo real em mídia"
    s["lede"] = ("Quanto cada canal de mídia realmente gera de receita, medido com um teste geográfico e um modelo de "
                 "mix de mídia, e como dividir a verba do próximo mês para a Tecelã Tecidos.")

    if confident:
        s["h_resumo"] = (f"Com a mesma verba, {brl_short(a['gain_mean'])} a mais de receita por mês. "
                         "O teste geográfico é o que permite dizer de onde tirar.")
    elif a:
        s["h_resumo"] = "A verba já está bem dividida: mexer agora traria pouco ganho e muita incerteza."
    else:
        s["h_resumo"] = "Resumo"
    takeaways = []
    if g:
        takeaways.append(
            f"<strong>A Meta gera receita de verdade.</strong> Desligada por {round(g['test_days'] / 7)} semanas em "
            f"{len(g['treated'])} estados, a receita ali caiu {pct(-g['relative_lift_mean'], 1)}: {brl_short(g['lost_revenue_mean'])} "
            f"perdidos, ou {per_real(g['roi_mean'])} para cada real que deixou de ser investido."
            if g.get("decision", {}).get("verdict") in ("channel_is_incremental", "real_but_small") else
            "<strong>O teste da Meta não foi conclusivo.</strong> O modelo fica só com o histórico, e a recomendação "
            "precisa ser lida com mais cautela.")
    if u.get("meta") and c.get("meta") and u.get("tiktok") and c.get("tiktok"):
        takeaways.append(
            f"<strong>Sem o teste, o modelo misturava Meta e TikTok.</strong> Os dois sobem e descem juntos; só com o "
            f"histórico, a Meta ficava com {per_real(u['meta']['roi_mean'])} por real e o TikTok com "
            f"{per_real(u['tiktok']['roi_mean'])}. Com o teste: {per_real(c['meta']['roi_mean'])} e {per_real(c['tiktok']['roi_mean'])}.")
    if a and (ups or downs):
        takeaways.append(
            f"<strong>Onde mexer.</strong> Levar verba de {listing([label(x) for x in downs[:2]]) or '—'} para "
            f"{listing([label(x) for x in ups[:2]]) or '—'}: em {pct(a['prob_better'])} dos cenários do modelo a nova divisão "
            f"rende mais que a atual (ganho entre {brl_short(a['gain_low'])} e {brl_short(a['gain_high'])} no mês).")
    s["takeaways"] = "".join(f"<li>{t}</li>" for t in takeaways)

    # 03 problem
    r = (sp.get("corr") or {}).get("meta|tiktok")
    if sp.get("meta") and sp.get("tiktok"):
        ratio = sum(sp["tiktok"]) / max(sum(sp["meta"]), 1)
        if r is not None and r >= 0.7:
            s["h_problema"] = (f"A verba do TikTok acompanha a da Meta todos os dias (correlação de {_num(r, 2)}): "
                               "olhando só o histórico, não dá para saber qual dos dois vendeu")
        else:
            s["h_problema"] = "Meta e TikTok têm verbas que variam de forma independente o suficiente para o modelo separá-los"
        s["d_problema"] = (f"Investimento semanal, em R$. O TikTok recebe em média {pct(ratio)} do que a Meta recebe, comprado "
                           "pela mesma equipe e no mesmo plano. Quando os dois sobem juntos e as vendas sobem, qualquer divisão "
                           "do crédito explica os dados igualmente bem.")
    else:
        s["h_problema"] = s["d_problema"] = ""

    # 04 test
    if g:
        verdict = g.get("decision", {}).get("verdict")
        if verdict in ("channel_is_incremental", "real_but_small"):
            s["h_teste"] = (f"Desligar a Meta em {len(g['treated'])} estados por {round(g['test_days'] / 7)} semanas derrubou a "
                            f"receita ali em {pct(-g['relative_lift_mean'], 1)}")
        else:
            s["h_teste"] = f"O teste geográfico da Meta foi {VERDICTS.get(verdict, verdict)}"
        s["d_teste"] = (f"Receita semanal dos estados testados ({', '.join(g['treated'])}). A linha azul é o que aconteceu; a "
                        "cinza tracejada é o que teria acontecido com a Meta ligada, montada com os estados que seguiram o "
                        "plano (controle sintético). A faixa sombreada cobre o teste e 2 semanas de resfriamento.")
        s["callout_teste"] = (
            f"<h3>O teste, em números</h3><p><span class=\"verdict{'' if verdict == 'channel_is_incremental' else ' verdict-weak'}\">"
            f"{esc(VERDICTS.get(verdict, verdict))}</span></p>"
            f"<p>De {date_br(g['start'])} a {date_br(g['end'])}, a Meta ficou desligada em {', '.join(g['treated'])} "
            f"({pct(g['treated_spend_share'])} da verba da Meta). A loja deixou de investir {brl_short(g['spend_removed'])} e "
            f"perdeu {brl_short(g['lost_revenue_mean'])} de receita (intervalo de 95%: {brl_short(g['lost_revenue_low'])} a "
            f"{brl_short(g['lost_revenue_high'])}), contando o resfriamento. Cada real a menos custou "
            f"{per_real(g['roi_mean'])} de receita. Uma segunda leitura, por diferença em diferenças, dá "
            f"{pct(-g['did']['relative_lift_mean'], 1)} de queda.</p>")
    else:
        s["h_teste"] = s["d_teste"] = s["callout_teste"] = ""

    # 05 calibration
    if u and c:
        both = [ch for ch in c if ch in u]
        moved = sorted(both, key=lambda ch: -abs(c[ch]["roi_mean"] - u[ch]["roi_mean"]))[:2]
        s["h_calib"] = "Com o teste, " + " e ".join(
            f"{label(ch)} vai de {per_real(u[ch]['roi_mean'])} para {per_real(c[ch]['roi_mean'])} por real" for ch in moved)
        if ev.get("uncalibrated") and ev.get("calibrated"):
            s["d_calib"] = (f"Receita incremental por real investido, por canal. Esquerda: o modelo só com o histórico; meio: "
                            f"com o teste; direita: o retorno verdadeiro que o simulador plantou. O erro médio contra a verdade cai "
                            f"de {per_real(ev['uncalibrated']['mean_abs_roi_error'])} para "
                            f"{per_real(ev['calibrated']['mean_abs_roi_error'])} por real.")
        else:
            s["d_calib"] = "Receita incremental por real investido, por canal, antes e depois do teste."
    elif u:
        s["h_calib"] = "Retorno por real investido, por canal (modelo só com o histórico)"
        s["d_calib"] = "O teste não foi conclusivo, então não houve calibração nesta execução."
    else:
        s["h_calib"] = s["d_calib"] = ""

    # 06 saturation
    cv = (d.get("curves") or {}).get(kind or "", {})
    if cv:
        def at(k):
            return int(np.argmin(np.abs(np.asarray(k["spend"]) - k["current"])))
        marg = sorted(((ch, cv[ch]["marginal"][at(cv[ch])]) for ch in cv), key=lambda x: -x[1])
        (top, mt), (bot, mb) = marg[0], marg[-1]
        s["h_curvas"] = (f"O próximo real rende {per_real(mt)} em {label(top)} e {per_real(mb)} em {label(bot)}"
                         if mt > 1.5 * mb else "O próximo real rende parecido em todos os canais")
        s["order_curves"] = json.dumps([ch for ch, _ in marg])
    else:
        s["h_curvas"], s["order_curves"] = "", "[]"

    # 07 recommendation
    if a:
        mv = _moves(a)
        moved_total = sum(m["delta"] for m in mv if m["delta"] > 0)
        s["h_reco"] = (f"Mover {brl_short(moved_total)} no mês: mais {listing([label(x) for x in ups[:2]])}, "
                       f"menos {listing([label(x) for x in downs[:2]])}" if confident and ups and downs else
                       "Manter a divisão atual e medir o próximo canal")
        s["d_reco"] = (f"Verba total fixa em {brl_short(a['total_budget'])} para {a['horizon_days']} dias. Cada canal pode ir de 50% a "
                       "150% do que recebe hoje: fora disso o modelo estaria chutando níveis de investimento que nunca viu. "
                       f"Receita incremental esperada sobe de {brl_short(a['revenue_current']['mean'])} para "
                       f"{brl_short(a['revenue_recommended']['mean'])}.")
        # next test: the channel (other than the one tested) with the widest relative ROI interval
        tested = g.get("channel") if g else None
        cand = sorted((r for ch, r in main.items() if ch != tested and r["roi_mean"] > 0),
                      key=lambda r: -(r["roi_high"] - r["roi_low"]) / r["roi_mean"])
        nxt = cand[0]["channel"] if cand else None
        reco = []
        for m in sorted(mv, key=lambda m: -m["delta"])[:2]:
            if m["delta"] > 0:
                reco.append((f"Aumentar {label(m['channel'])} para {brl_short(m['recommended_total'])} no mês",
                             f"{pct(m['change_pct'], signed=True)} sobre hoje. Ali o próximo real ainda rende "
                             f"{per_real(m['marginal_roi_recommended'])}"
                             f"{', e o canal fica no teto de 150%' if m['at_upper_bound'] else ''}.",
                             "receita incremental do canal no mês seguinte, comparada à previsão do modelo."))
        for m in sorted(mv, key=lambda m: m["delta"])[:1]:
            if m["delta"] < 0:
                reco.append((f"Reduzir {label(m['channel'])} para {brl_short(m['recommended_total'])} no mês",
                             f"{pct(m['change_pct'], signed=True)} sobre hoje: o retorno do próximo real ali é de "
                             f"{per_real(m['marginal_roi_current'])} no nível atual.",
                             "vendas totais da loja nas semanas seguintes ao corte."))
        if nxt:
            rr = main[nxt]
            reco.append((f"Rodar o próximo teste geográfico em {label(nxt)}",
                         f"É o canal com o retorno mais incerto: entre {per_real(rr['roi_low'])} e {per_real(rr['roi_high'])} por real. "
                         "Um teste nele faz pelo canal o que o da Meta fez pela Meta.",
                         "mesmo desenho: desligar o canal num grupo de estados e comparar com o controle sintético."))
        s["reco_items"] = "".join(f"<li><h3>{esc(t)}</h3><p>{esc(b)}</p><p class=\"reco-meta\"><span>Como medir</span>"
                                  f"{esc(how)}</p></li>" for t, b, how in reco)
        s["h_incerteza"] = (f"Em {pct(a['prob_better'])} dos cenários do modelo a nova divisão rende mais que a atual"
                            if a["prob_better"] >= 0.5 else
                            f"Só {pct(a['prob_better'])} dos cenários dão ganho: a recomendação não é segura")
        s["d_incerteza"] = (f"Cada barra conta quantos cenários plausíveis do modelo dão aquele ganho no mês. Azul: cenários em "
                            f"que a nova divisão ganha da atual. Ganho esperado de {brl_short(a['gain_mean'])}; em 90% dos cenários, "
                            f"entre {brl_short(a['gain_low'])} e {brl_short(a['gain_high'])}.")
    else:
        s.update({k: "" for k in ("h_reco", "d_reco", "reco_items", "h_incerteza", "d_incerteza")})

    # summary block (server-rendered)
    stats = []
    if a:
        hero = (f'<div class="hero-stat"><p class="stat-label">Receita a mais por mês, com a mesma verba</p>'
                f'<p class="hero-value">{brl_short(a["gain_mean"])}</p><p class="stat-note">esperado com a nova divisão; em 90% dos '
                f'cenários entre {brl_short(a["gain_low"])} e {brl_short(a["gain_high"])}.</p></div>')
        stats.append(("Chance de a nova divisão render mais", pct(a["prob_better"]), "nos cenários plausíveis do modelo", ""))
    else:
        hero = ""
    if g:
        stats.append(("Queda de receita sem a Meta", pct(-g["relative_lift_mean"], 1),
                      f"nos {len(g['treated'])} estados do teste", ""))
    if c.get("meta"):
        stats.append(("Retorno da Meta, com o teste", per_real(c["meta"]["roi_mean"]),
                      f"por real; só com o histórico, {per_real(u['meta']['roi_mean'])}" if u.get("meta") else "por real", ""))
    if c.get("tiktok"):
        stats.append(("Retorno do TikTok, com o teste", per_real(c["tiktok"]["roi_mean"]),
                      f"por real; só com o histórico, {per_real(u['tiktok']['roi_mean'])}" if u.get("tiktok") else "por real",
                      " stat-warn"))
    s["summary"] = hero + '<div class="stats">' + "".join(
        f'<div class="stat{cls}"><p class="stat-label">{esc(lab)}</p><p class="stat-value">{val}</p>'
        f'<p class="stat-note">{esc(note)}</p></div>' for lab, val, note, cls in stats[:4]) + "</div>"

    # glossary example
    s["ex_meta_roi"] = per_real(main["meta"]["roi_mean"]) if main.get("meta") else "—"
    s["truth_note"] = ("A verdade aparece só no capítulo 05, para mostrar o quanto o modelo acertou." if truth else
                       "Nesta execução a verdade do simulador não estava disponível, então o capítulo 05 não a mostra.")
    return s


def tables(d: dict) -> dict[str, str]:
    t: dict[str, str] = {}
    sp = d.get("spend") or {}
    if sp.get("week"):
        # quarters keep the table short; the chart shows every week
        import pandas as pd
        df = pd.DataFrame({"week": pd.to_datetime(sp["week"]), "meta": sp["meta"], "tiktok": sp["tiktok"]})
        q = df.groupby(df.week.dt.to_period("Q"))[["meta", "tiktok"]].sum()
        t["table_problema"] = table("Investimento por trimestre", ["Trimestre", "Meta Ads", "TikTok Ads", "TikTok ÷ Meta"],
                                    [[f"{p.quarter}º tri {p.year}", brl_short(r.meta), brl_short(r.tiktok),
                                      pct(r.tiktok / r.meta if r.meta else np.nan)] for p, r in q.iterrows()])
    else:
        t["table_problema"] = ""
    g = d.get("geolift") or {}
    if g.get("series"):
        se = g["series"]
        first = se["post"].index(True) if True in se["post"] else len(se["week"])
        keep = range(max(0, first - 6), len(se["week"]))  # 6 weeks before the test, then the test and cool-down
        t["table_teste"] = table("Receita semanal dos estados testados", ["Semana", "Real", "Sem o teste (sintético)", "Diferença"],
                                 [[date_br(se["week"][i]) + (" · teste" if se["post"][i] else ""), brl(se["observed"][i]),
                                   brl(se["synthetic"][i]), brl(se["observed"][i] - se["synthetic"][i])] for i in keep])
    else:
        t["table_teste"] = ""
    u, c = _roi(d, "uncalibrated"), _roi(d, "calibrated")
    truth = {r["channel"]: r for r in d.get("roi_vs_truth") or []}
    if u:
        chs = sorted(u, key=lambda ch: -(c.get(ch) or u[ch])["roi_mean"])
        cols = ["Canal", "Investimento", "Só histórico", "Com o teste", "Faixa (94%)", "Verdade (simulador)"]
        t["table_calib"] = table("Receita incremental por real investido no período", cols, [
            [name(ch), brl_short(u[ch]["spend"]), per_real(u[ch]["roi_mean"]),
             per_real(c[ch]["roi_mean"]) if ch in c else "—",
             f"{per_real((c.get(ch) or u[ch])['roi_low'])} a {per_real((c.get(ch) or u[ch])['roi_high'])}",
             per_real(truth[ch]["roi_true"]) if ch in truth else "—"] for ch in chs])
    else:
        t["table_calib"] = ""
    kind, a = _allocation(d)
    if a:
        mv = sorted(_moves(a), key=lambda m: -m["recommended_total"])
        t["table_reco"] = table(f"Verba e receita incremental em {a['horizon_days']} dias",
                                ["Canal", "Hoje", "Recomendado", "Variação", "Receita incremental", "Retorno médio", "Próximo real"],
                                [[name(m["channel"]), brl_short(m["current_total"]),
                                  f"<strong>{brl_short(m['recommended_total'])}</strong>",
                                  f'<span class="{"up" if m["delta"] > 0 else ""}">{pct(m["change_pct"], signed=True)}</span>',
                                  brl_short(m["revenue_recommended"]), per_real(m["roi_recommended"]),
                                  per_real(m["marginal_roi_recommended"])] for m in mv])
        t["table_curvas"] = table("Retorno no investimento atual", ["Canal", "Investimento por dia", "Retorno médio", "Próximo real"],
                                  [[name(m["channel"]), brl(m["current_daily"]),
                                    per_real(m["revenue_current"] / max(m["current_daily_at_budget"] * a["horizon_days"], 1e-9)),
                                    per_real(m["marginal_roi_current"])]
                                   for m in sorted(mv, key=lambda m: -m["marginal_roi_current"])])
        draws = np.asarray((d.get("gain_draws") or {}).get(kind, []))
        t["table_incerteza"] = table("Ganho da nova divisão no mês, por cenário do modelo", ["Cenário", "Ganho"],
                                     [["Pessimista (5%)", brl_short(a["gain_low"])], ["Esperado", brl_short(a["gain_mean"])],
                                      ["Otimista (95%)", brl_short(a["gain_high"])],
                                      ["Cenários com ganho", pct(a["prob_better"])]] +
                                     ([["Cenários avaliados", _num(len(draws))]] if len(draws) else []))
    else:
        t["table_reco"] = t["table_curvas"] = t["table_incerteza"] = ""
    dg = (d.get("diagnostics") or {}).get("models") or {}
    t["table_diag"] = table("Convergência e ajuste de cada modelo", ["Modelo", "r-hat máx.", "ESS mín.", "Divergências",
                                                                     "Erro diário (WAPE)", "Cobertura 94%"],
                            [[{"calibrated": "Com o teste", "uncalibrated": "Só histórico"}[k], _num(m["diagnostics"]["rhat_max"], 3),
                              _num(m["diagnostics"]["ess_bulk_min"]), str(m["diagnostics"]["divergences"]),
                              pct(m["checks"]["posterior_predictive"]["wape"], 1),
                              pct(m["checks"]["posterior_predictive"].get("coverage_94"))] for k, m in dg.items()]) if dg else ""
    bt = (d.get("evaluation") or {}).get("backtest") or []
    t["table_backtest"] = table("Previsão fora da amostra (treino até a data de corte, previsão das semanas seguintes)",
                                ["Período previsto", "Erro diário (WAPE)", "Erro no total", "Cobertura 94%"],
                                [[f"{date_br(b['test_start'])} a {date_br(b['test_end'])}", pct(b["wape"], 1),
                                  pct(b["revenue_total_error_pct"], 1, signed=True), pct(b.get("coverage_94"))] for b in bt]) if bt else ""
    return t


def facts(d: dict) -> dict[str, str]:
    f = d.get("facts") or {}
    return {"period_long": f"{date_br(f['start'])} a {date_br(f['end'])}" if f else "—",
            "months": _num(f.get("months", 0)), "revenue": brl_short(f.get("revenue")),
            "spend": brl_short(f.get("spend")), "orders": _num(f.get("orders", 0)),
            "channels_n": str(len(LABELS))}


# --- page -----------------------------------------------------------------------------

def _symbol_path() -> str:
    return (ROOT / "assets" / "brand" / "symbol_path.txt").read_text().split("\n", 1)[1].strip()


def _symbol() -> str:
    return (f'<svg class="mark" viewBox="{SYMBOL_VIEWBOX}" aria-hidden="true" focusable="false">'
            f'<path d="{_symbol_path()}" fill-rule="evenodd"/></svg>')


def _version(*paths: Path) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.read_bytes())
    return h.hexdigest()[:10]


def slots(d: dict) -> dict[str, str]:
    values = {
        "version_css": _version(ASSETS / "styles.css"), "version_js": _version(ASSETS / "app.js"),
        "plotly_file": PLOTLY.name, "symbol": _symbol(),
        **facts(d), **story(d), **tables(d),
        "data": json.dumps(d, ensure_ascii=False, separators=(",", ":"), sort_keys=True).replace("</", "<\\/"),
        "geo": (ASSETS / "br_ufs.geojson").read_text(encoding="utf-8").replace("</", "<\\/"),
    }
    raw = {"data", "geo", "symbol", "order_curves", "takeaways", "reco_items", "callout_teste", "summary"} | {
        k for k in values if k.startswith("table_")}
    return {k: (nbsp(v) if k not in raw and isinstance(v, str) else v) for k, v in values.items()}


def render(d: dict) -> str:
    filled = slots(d)
    text = (ASSETS / "index.html").read_text(encoding="utf-8")

    def fill(m: re.Match) -> str:
        key = m.group(1)
        if key not in filled:
            raise KeyError(f"template asks for [[{key}]], which page.slots() does not provide")
        return filled[key]

    return re.sub(r"\[\[(\w+)\]\]", fill, text)


def build(d: dict, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render(d), encoding="utf-8")
    for n in ("styles.css", "app.js"):
        shutil.copyfile(ASSETS / n, out / n)
    target = out / PLOTLY.name
    if not target.exists() or target.read_bytes() != PLOTLY.read_bytes():
        shutil.copyfile(PLOTLY, target)
    for old in out.glob("*"):
        if old.name not in {"index.html", "styles.css", "app.js", PLOTLY.name, "favicon.svg"}:
            old.unlink()
    (out / "favicon.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-14 -14 156 128"><rect x="-14" y="-14" width="156" '
        f'height="128" rx="24" fill="#050505"/><path d="{_symbol_path()}" fill="#F6F5F0" fill-rule="evenodd"/></svg>',
        encoding="utf-8")
    return out / "index.html"
