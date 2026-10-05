"""Temas de los mensajes que el asistente no supo atender, para el administrador: grupos con su tamaño y sus términos
característicos. Nunca devuelve un mensaje.

TF-IDF de palabras y pares de palabras + k-means (scikit-learn, sin LLM). Privacidad:
- se quitan números (montos, fechas, identificadores) y lo que no sea letras;
- un término solo entra al vocabulario si aparece en al menos `min_group` mensajes, y solo se publica en un grupo si al menos
  `min_group` mensajes de ese grupo lo contienen: una frase rara de una persona no puede salir;
- un grupo con menos de `min_group` mensajes no se publica (se suma a "sin grupo").
Es exploratorio: sirve para ver qué piden los clientes fuera de lo que el chat atiende, no para decidir nada.
"""
from __future__ import annotations

import re
import unicodedata

STOP = set("""a al algo ante aqui asi aun con como cual cuando de del desde donde el ella ellos en era eres es esa ese eso esta estas este
esto estoy fue ha hace hacer han hasta hay la las le les lo los mas me mi mis mucho muy nada ni no nos o os para pero por porque que quien
se ser si sin sobre su sus te tengo tiene todo tu tus un una uno unos y ya yo usted ustedes hola buenas buenos dias tardes noches gracias porfa favor
ao aos as da das do dos e ela ele em essa esse isso esta este eu foi mais mas meu minha na nas nao nem no nos num numa o os ou para pela pelo
por pra pro qual quando que quem sao se sem ser seu sua tambem te tem tenho um uma voce voces ola oi bom boa dia tarde noite obrigado obrigada""".split())
WORD = re.compile(r"[a-zñç]{3,}")
ID_LIKE = re.compile(r"^\W*[A-Za-z]{2,5}[-_][A-Za-z0-9]{4,}\W*$")


def normalize(text: str) -> str:
    # fuera las palabras con dígitos o con forma de identificador (CLI-…, TRX-…): montos, fechas, cuentas y referencias
    text = " ".join(w for w in text.split() if not any(ch.isdigit() for ch in w) and not ID_LIKE.match(w))
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn" or c == "̃")       # sin tildes; conserva la virgulilla de ñ
    t = unicodedata.normalize("NFC", t).replace("ã", "a").replace("õ", "o")
    return " ".join(w for w in WORD.findall(t) if w not in STOP)


def topic_clusters(messages: list[str], min_group: int = 5, max_clusters: int = 8, seed: int = 0) -> dict:
    """{'messages': N, 'clusters': [{'size', 'share', 'terms'}], 'unclustered': n}. Sin mensajes en la salida."""
    docs = [normalize(m) for m in messages if m and m.strip()]
    n = len(docs)
    empty = {"messages": n, "clusters": [], "unclustered": n}
    if n < 2 * min_group:
        return empty
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    try:
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=min_group, sublinear_tf=True)
        x = vec.fit_transform(docs)
    except ValueError:                           # ningún término llega a min_group mensajes
        return empty
    has_terms = x.getnnz(axis=1) > 0
    rows = [i for i in range(n) if has_terms[i]]
    if len(rows) < 2 * min_group:
        return empty
    xs = x[rows]
    k = max(2, min(max_clusters, len(rows) // (3 * min_group), xs.shape[1]))
    labels = KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(xs)
    names = vec.get_feature_names_out()
    clusters: list[dict] = []
    published = 0
    for c in range(k):
        idx = [i for i, lab in enumerate(labels) if lab == c]
        if len(idx) < min_group:
            continue
        sub = xs[idx]
        df = (sub > 0).sum(axis=0).A1                       # mensajes del grupo que contienen cada término
        weight = sub.sum(axis=0).A1
        terms = [names[j] for j in sorted(range(len(names)), key=lambda j: -weight[j]) if df[j] >= min_group][:6]
        if not terms:
            continue
        # un par de palabras ya dice lo que dicen sus palabras sueltas: se quitan las repetidas
        kept: list[str] = []
        for t in terms:
            if not any(set(t.split()) <= set(o.split()) for o in kept):
                kept.append(t)
        clusters.append({"size": len(idx), "share": round(len(idx) / n, 4), "terms": kept[:5]})
        published += len(idx)
    clusters.sort(key=lambda c: int(c["size"]), reverse=True)
    return {"messages": n, "clusters": clusters, "unclustered": n - published}
