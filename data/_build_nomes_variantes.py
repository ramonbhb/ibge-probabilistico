"""Gera data/nomes_variantes.csv — rode da raiz: python data/_build_nomes_variantes.py

O CSV entra só no caminho fonético (`nome_completo` limpo não muda).
"""

from __future__ import annotations

from pathlib import Path

# canonico -> variantes (só o que muda; o canônico não entra — o replace
# deixa o nome como está se não achar variante)
# CAMILY ≠ KEMELI ≠ CAMILA
# JULIA ≠ GIULIA (nome italiano); JHULIA/JIULIA são grafia de JULIA
# J+H no meio (JHONATAN, JHENIFER) = o mesmo nome, H ornamental
GRAFIA: dict[str, list[str]] = {
    "ESTER": ["ESTHER", "ISTER", "HESTER"],
    "ETEVELVINA": [
        "ITELVINA", "ETELVINA", "ESTEVELVINA", "ESTELVINA",
    ],
    "LOURENCO": ["LORENCO", "LOURENZO"],
    "KEMELI": [
        "KEMELY", "KEMELLY", "KEMELI",
        "KEMILI", "KEMILY", "KEMILLY", "KEMILLI",
        "KEMYLLY", "KEMYLI", "KEMYLY", "KEMYLLE",
        "KEMILE", "KEMILEY", "KEMILEI",
    ],
    "CAMILY": [
        "CAMILI", "CAMILLY", "CAMILLI", "CAMYLLY", "CAMYLI", "CAMYLY",
        "CAMILEY", "CAMILEI",
        "KAMILY", "KAMILI", "KAMILLY", "KAMILLI", "KAMYLLY", "KAMYLI",
        "KAMILEY", "KAMILEI",
    ],
    "CAMILA": [
        "KAMILA", "CAMILLA", "KAMILLA", "CAMYLA", "KAMYLA",
    ],
    "YASMIN": [
        "IASMIN", "YASMIM", "IASMIM",
        "YASMYN", "IASMYN", "YAZMIN", "IAZMIN", "YASMINN",
    ],
    "MAYARA": ["MAIARA", "MAYARA"],
    "NAYARA": ["NAIARA", "NAYARA"],
    "THAIS": ["TAIS", "THAYS", "TAYS", "THAIZ", "TAIZ", "TAHIS"],
    "CAIO": ["KAIO", "CAYO", "KAYO"],
    "KAUA": ["CAUA"],
    "KAUAN": ["CAUAN", "KAUANN", "CAUANN"],
    "KAUANE": ["CAUANE", "KAUANY", "CAUANY", "KAUANNY", "CAUANNY"],
    "KAIQUE": [
        "CAIQUE", "KAYQUE", "CAYQUE", "KAIKE", "KAYKE", "KAYKY",
        "KAIKY", "CAIKE", "CAYKE",
    ],
    "KAUE": ["CAUE"],
    "RYAN": ["RIAN", "RYANN", "RIANN", "RHIAN"],
    "IAN": ["YAN"],
    "WILLIAN": [
        "WILIAN", "WILLIAM", "UILLIAN", "UILIAN", "WILIAM", "UILIAM",
        "WILLIANS", "WILLYAN", "WILLYAM",
    ],
    "WESLEY": ["WESLEI", "UESLEI", "UESLEY", "WESLLEY", "WESLI", "WESLLY"],
    "WELLINGTON": [
        "WELINGTON", "UELLINGTON", "UELINGTON", "WELLIGTON", "WELIGTON",
        "WELLINTON",
    ],
    "WAGNER": ["VAGNER"],
    "WILSON": ["VILSON", "UILSON"],
    "WALLACE": ["UALLACE", "WALACE", "UALACE", "WALLAS", "WALAS"],
    "WANDERSON": ["VANDERSON", "UANDERSON"],
    "WANDERLEY": ["VANDERLEI", "WANDERLEI", "VANDERLEY"],
    "WASHINGTON": ["UASHINGTON", "WASHIGTON"],
    "WENDEL": ["WENDELL", "VENDEL", "VENDELL", "UENDEL"],
    "CRISTIAN": [
        "CHRISTIAN", "CRYSTIAN", "KRISTIAN", "CRHISTIAN", "CRISTYAN",
        "CHRISTYAN", "KHRYSTIAN",
    ],
    "CRISTINA": ["CHRISTINA", "CRYSTINA", "KRISTINA"],
    "CRISTIANE": ["CHRISTIANE", "CRISTIANNE", "CHRISTIANNE"],
    "CRISTIANO": ["CHRISTIANO"],
    "MICHAEL": ["MIKAEL", "MYKAEL", "MIKHAEL", "MICHAEL"],
    "RAQUEL": ["RACHEL", "RAKEL"],
    "MATHEUS": ["MATEUS", "MATTEUS"],
    "THIAGO": ["TIAGO", "TYAGO", "THYAGO"],
    "NATALIA": ["NATHALIA", "NATHALYA", "NATALYA"],
    "NATHAN": ["NATAN", "NATHANN"],
    "THEO": ["TEO"],
    "FELIPE": ["FELIPPE", "PHILIPE", "PHILIPPE", "FILIPE", "FELIPI", "PHILIPI"],
    "RAFAEL": ["RAPHAEL", "RAFFAEL", "RAFAHEL"],
    "RAFAELA": ["RAPHAELA", "RAFFAELA", "RAFAELLA", "RAPHAELLA"],
    "VITOR": ["VICTOR", "VITTOR"],
    "VITORIA": ["VICTORIA", "VITTORIA"],
    "SOFIA": ["SOPHIA", "SOFFIA", "SOPHYA"],
    "LIVIA": ["LYVIA", "LIVYA", "LYVYA"],
    "GIOVANNA": ["GIOVANA", "GEOVANA", "GEOVANNA", "JOVANA", "JOVANNA"],
    "GIOVANI": ["GIOVANNI", "GEOVANI", "GEOVANNI", "JOVANI", "JOVANNI"],
    "ISABELA": [
        "ISABELLA", "IZABELA", "IZABELLA", "YSABELA", "YSABELLA",
    ],
    "ISABEL": ["IZABEL", "YZABEL", "ISABELL"],
    "ISABELY": ["ISABELLY", "IZABELY", "IZABELLY", "YSABELY", "YSABELLY"],
    "ISADORA": ["IZADORA", "YSADORA"],
    "LETICIA": ["LETICYA", "LETHICIA", "LETISSIA"],
    "PATRICIA": ["PATRICYA", "PATHRICIA"],
    "JULIA": [
        "JULYA", "JULLIA", "JULLYA", "JHULIA", "JHULLIA", "JIULIA", "JHIULIA",
    ],
    "GIULIA": ["GIULLIA", "GIULYA"],
    "JULIANO": ["JHULIANO", "JIULIANO"],
    "ALINE": ["ALLYNE", "ALYNE", "ALLINE"],
    "ELAINE": ["ELAYNE", "ELLAINE"],
    "DAIANE": ["DAYANE", "DAYANNE", "DAIANNE", "DAHIANE"],
    "SUELEN": ["SUELLEN"],
    "JAQUELINE": [
        "JACKELINE", "JAKELINE", "JACQUELINE", "JAQUELLINE", "JACKELINE",
    ],
    "GEISA": ["GEYSA", "JEISA", "JEYSA", "GEIZA", "GEYZA"],
    "GEISE": ["GEYSE", "JEISE", "JEYSE"],
    "GISELE": ["GIZELE", "GISELLE", "JISELE", "GISELI", "GIZELI", "GISELLI"],
    "JANAINA": ["JANAYNA", "JANNAINA"],
    "JESSICA": [
        "JESSYCA", "GESSICA", "JESSYKA", "GESSYCA", "JEZICA",
        "JHESSICA", "JHESSYCA",
    ],
    "JEFFERSON": [
        "JEFERSON", "JEFERSSON", "GEFERSON", "JEFFERSSON", "JEFERSEN",
        "JHEFERSON", "JHEFFERSON",
    ],
    "JENIFER": [
        "JENNIFER", "JENIFFER", "GENIFER", "JENNYFER", "JHENIFER",
        "JHENNIFER", "JHENIFFER",
    ],
    "JONATHAN": [
        "JONATAN", "JHONATAN", "JOHNATAN", "JHONATHAN", "JOHNATHAN",
        "JONATHAM",
    ],
    "JONATAS": ["JONATHAS"],
    "JACKSON": ["JAKSON", "JACSON", "JECKSON", "JACKSOM"],
    "JEAN": ["GEAN", "JHAN", "JHEAN"],
    "JOAO": ["JHOAO"],
    "EDSON": ["EDISON", "EDDISON"],
    "CLEITON": [
        "CLAYTON", "KLEITON", "KLAYTON", "CLAITON", "KLAITON",
    ],
    "CLEBER": ["KLEBER"],
    "DEBORA": ["DEBHORA", "DEBORAH", "DEBBORA"],
    "DENISE": ["DENIZE"],
    "DIEGO": ["DYEGO"],
    "DOUGLAS": ["DUGLAS", "DOUGUAS"],
    "DAVI": ["DAVID", "DHAVI"],
    "EMILY": [
        "EMILI", "EMILLY", "EMMILLI", "EMMILY", "EMELI", "EMELLY",
        "EMILE", "EMILEY", "EMILIE",
    ],
    "EVELYN": [
        "EVELIN", "EVELYNE", "EVELLYN", "EVELLIN", "EVELIM",
        "HEVELYN",
    ],
    "EMANUEL": ["EMANNUEL", "EMMANUEL"],
    "MANOEL": ["MANUEL"],
    "EMANUELE": [
        "EMANUELLE", "EMANUELLY", "EMANUELY", "EMANNUELLE", "EMANUELI",
    ],
    "MILENA": ["MYLENA", "MILENNA", "MYLENNA"],
    "MELISSA": ["MELYSSA"],
    "MAISA": ["MAYSA", "MAISSA", "MAYSSA"],
    "MAITE": ["MAYTE", "MAITHE", "MAYTHE"],
    "LORRANE": ["LORRANY", "LORRANNI", "LORANE", "LORANY"],
    "CAROLINA": ["CAROLYNA", "KAROLINA", "KAROLYNA"],
    "CAROLINE": ["CAROLYNE", "KAROLINE", "KAROLYNE"],
    "GABRIELA": ["GABRIELLA"],
    "GABRIELY": [
        "GABRIELLY", "GABRIELLI", "GABRIELI", "GABRIELE",
    ],
    "ALANA": ["ALLANA", "ALANNA", "ALLANNA"],
    "ANDRESSA": ["ANDRESA"],
    "ANDREIA": ["ANDREYA"],
    "ALEXANDRE": [
        "ALEKSANDRE", "ALESSANDRE", "ALEXSANDRE", "ALECSANDRE",
        "ALECSSANDRE",
    ],
    "ALESSANDRO": [
        "ALEXSANDRO", "ALEKSANDRO", "ALECSANDRO",
    ],
    "ALESSANDRA": ["ALEXSANDRA", "ALEKSANDRA"],
    "KEVIN": ["KEVEN", "KEVYN"],
    "LUCAS": ["LUKAS", "LUCCAS", "LUKKAS"],
    "LUCA": ["LUCCA"],
    "LUIZ": ["LUIS"],
    "LUIZA": ["LUISA"],
    "NICOLAS": ["NIKOLAS", "NICHOLAS", "NICOLLAS", "NIKOLLAS"],
    "NICOLE": ["NIKOLE", "NICOLLE", "NIKOLLE", "NYCOLE"],
    "MICHELE": ["MICHELLE", "MISHELLE", "MISHELE"],
    "MICHEL": ["MISHEL", "MICHELL"],
    "STEFANY": [
        "STEPHANY", "STEFANI", "STEPHANIE", "ESTEFANI", "ESTEFANY",
        "STEFANE", "STEPHANE", "STEFFANY", "ESTEFANE", "STEFANIE",
    ],
    "HELEN": ["HELLEN", "ELLEN", "ELEN"],
    "HELENA": ["ELENA", "HELLENA", "ELLENA"],
    "HELIO": ["ELIO"],
    "HEITOR": ["EITOR", "HEYTOR", "EYTOR"],
    "RUAN": ["RHUAN", "RUANN", "RHUANN"],
    "LUAN": ["LUANN"],
    "LAIS": ["LAYS", "LAIZ", "LAYZ", "LHAIS"],
    "RAISSA": ["RAYSSA", "RAISA", "RHAISSA", "RAYSA", "RHAYSSA"],
    "TAYNARA": ["TAINARA", "THAINARA", "THAYNARA"],
    "TAYNA": ["TAINA", "THAINA", "THAYNA"],
    "REBECA": ["REBECCA", "REBEKA", "REBEKKA"],
    "PIETRA": ["PYETRA", "PIETTRA"],
    "BENJAMIN": ["BENJAMIM"],
    "ISAQUE": ["ISAAC", "IZAQUE", "IZAAC", "ISAAK"],
    "ISMAEL": ["ISHMAEL", "IZMAEL", "YSMAEL"],
    "JOSIANE": ["JOZIANE", "JOSYANE", "JOCIANE"],
    "JOSIELE": ["JOZIELE", "JOSYELE", "JOCIELE"],
    "ROSILENE": ["ROZILENE", "ROSYLENE"],
    "ROSELI": ["ROSELY", "ROZELI", "ROSELEI"],
    "ROSANE": ["ROZANE"],
    "ROSEANE": ["ROZEANE"],
    "ROSANGELA": ["ROZANGELA"],
    "ROSEMEIRE": ["ROSIMEIRE", "ROZEMEIRE", "ROSEMEIRE"],
    "KELLY": ["KELI", "KELLI"],
    "KEILA": ["KEYLA", "KEILLA", "KEYLLA"],
    "SHEILA": ["SCHEILA", "CHEILA", "SHEYLA", "SCHEYLA"],
    "SHIRLEY": ["SHIRLEI", "CHIRLEI"],
    "MONIQUE": ["MONIKE", "MONICKE", "MONYQUE"],
    "MONICA": ["MONIKA"],
    "VERONICA": ["VERONIKA"],
    "TATIANE": ["TATYANE", "TATHIANE", "TATIANNE"],
    "TATIANA": ["TATHIANA", "TATYANA"],
    "PRISCILA": ["PRISCILLA", "PRISCYLA", "PRYSCILA"],
    "HELOISA": ["HELOYSA", "ELOISA", "ELOYSA", "HELOIZA", "ELOIZA"],
    "ELOA": ["ELOAH", "HELOA", "HELOAH"],
    "LISANDRA": ["LIZANDRA", "LYSANDRA"],
    "ALICE": ["ALLICE", "ALYCE"],
    "ALICIA": ["ALYCIA"],
    "SARA": ["SARAH", "SAHRA"],
    "TEREZA": ["TERESA", "THEREZA", "THERESA"],
    "CATARINA": ["CATHARINA", "KATARINA"],
    "KATERINE": [
        "KATHERINE", "CATHERINE", "KATARINE", "KATHARINE",
    ],
    "KATIA": ["CATIA", "KATHIA", "CATHIA", "KATYA"],
    "OLIVIA": ["OLYVIA"],
    "BIANCA": ["BYANCA", "BIANKA", "BYANKA"],
    "BRUNA": ["BRUNNA"],
    "BRUNO": ["BRUNNO"],
    "CHARLES": ["CHARLE", "CHARLEY", "CHARLEI", "CHARLLES"],
    "HENRIQUE": ["ENRIQUE", "HENRIKE"],
    "SAMUEL": ["SAMUELL", "SAMMUEL"],
    "DANIEL": ["DHANIEL", "DANYEL"],
    "DANIELA": ["DANIELLA", "DANYELA", "DHANIELA"],
    "DANIELE": ["DANIELLE", "DANIELLI", "DANIELI", "DANYELE"],
    "ADRIANE": ["ADRIANNE", "ADRIANI"],
    "JULIANE": ["JULIANNE", "JULYANE"],
    "JULIANA": ["JULYANA", "JHULIANA"],
    "POLIANA": ["POLYANA", "POLLYANA", "POLLYANNA"],
    "TAMIRES": [
        "THAMIRES", "TAMYRES", "THAMYRES", "TAMIRIS", "THAMIRIS",
    ],
    "SAMARA": ["SAMARRA"],
    "FATIMA": ["FATHIMA"],
}

COMPOSTO: dict[str, list[str]] = {
    "ROSA MARIA": ["ROSAMARIA"],
    "ANA MARIA": ["ANAMARIA"],
    "MARIA JOSE": ["MARIAJOSE"],
    "MARIA LUCIA": ["MARIALUCIA"],
    "MARIA ROSA": ["MARIAROSA"],
    "MARIA HELENA": ["MARIAHELENA"],
    "MARIA APARECIDA": ["MARIAAPARECIDA"],
    "ANA PAULA": ["ANAPAULA"],
    "ANA CLARA": ["ANACLARA"],
    "ANA CAROLINA": ["ANACAROLINA"],
    "ANA CAROLINE": ["ANACAROLINE"],
    "ANA BEATRIZ": ["ANABEATRIZ"],
    "ANA JULIA": ["ANAJULIA"],
    "ANA LUCIA": ["ANALUCIA"],
    "ANA LUISA": ["ANALUISA"],
    "ANA LUIZA": ["ANALUIZA"],
    "ANA LAURA": ["ANALAURA"],
    "ANA LIVIA": ["ANALIVIA"],
    "MARIA EDUARDA": ["MARIAEDUARDA"],
    "MARIA CLARA": ["MARIACLARA"],
    "MARIA FERNANDA": ["MARIAFERNANDA"],
    "MARIA LUIZA": ["MARIALUIZA"],
    "MARIA LUISA": ["MARIALUISA"],
    "MARIA CECILIA": ["MARIACECILIA"],
    "MARIA VITORIA": ["MARIAVITORIA"],
    "JOAO PAULO": ["JOAOPAULO"],
    "JOAO VITOR": ["JOAOVITOR", "JOAOVICTOR"],
    "JOAO PEDRO": ["JOAOPEDRO"],
    "JOAO GABRIEL": ["JOAOGABRIEL"],
    "JOAO LUCAS": ["JOAOLUCAS"],
    "LUIZ FERNANDO": ["LUIZFERNANDO", "LUISFERNANDO"],
    "LUIZ GUILHERME": ["LUIZGUILHERME", "LUISGUILHERME"],
    "LUIZ HENRIQUE": ["LUIZHENRIQUE", "LUISHENRIQUE"],
    "LUIZ FELIPE": ["LUIZFELIPE", "LUISFELIPE"],
    "CARLOS ALBERTO": ["CARLOSALBERTO"],
    "CARLOS EDUARDO": ["CARLOSEDUARDO"],
    "CARLOS HENRIQUE": ["CARLOSHENRIQUE"],
    "JOSE CARLOS": ["JOSECARLOS"],
    "JOSE ANTONIO": ["JOSEANTONIO"],
    "JOSE LUIZ": ["JOSELUIZ", "JOSELUIS"],
    "JOSE APARECIDO": ["JOSEAPARECIDO"],
    "PEDRO HENRIQUE": ["PEDROHENRIQUE"],
    "PEDRO LUCAS": ["PEDROLUCAS"],
    "GABRIEL HENRIQUE": ["GABRIELHENRIQUE"],
}


def _linhas() -> list[tuple[str, str, str]]:
    visto_var: dict[str, str] = {}
    out: list[tuple[str, str, str]] = []

    def add(variante: str, canonico: str, tipo: str) -> None:
        variante = variante.replace("  ", " ").strip().upper()
        canonico = canonico.replace("  ", " ").strip().upper()
        if not variante or not canonico:
            raise ValueError("vazio")
        if variante == canonico:
            return
        outro = visto_var.get(variante)
        if outro and outro != canonico:
            raise SystemExit(
                f"variante {variante!r} aponta para {outro!r} e {canonico!r}"
            )
        if outro == canonico:
            return
        visto_var[variante] = canonico
        out.append((variante, canonico, tipo))

    for canonico, variantes in GRAFIA.items():
        for v in variantes:
            add(v, canonico, "grafia")
    for canonico, variantes in COMPOSTO.items():
        for v in variantes:
            add(v, canonico, "composto")
    out.sort(key=lambda r: (r[1], r[2], r[0]))
    return out


def main() -> None:
    destino = Path(__file__).resolve().parent / "nomes_variantes.csv"
    linhas = _linhas()
    with destino.open("w", encoding="utf-8", newline="\n") as f:
        f.write("variante,canonico,tipo\n")
        for a, b, t in linhas:
            f.write(f"{a},{b},{t}\n")
    n_g = sum(1 for _, _, t in linhas if t == "grafia")
    n_c = sum(1 for _, _, t in linhas if t == "composto")
    print(f"{destino.name}: {len(linhas)} linhas (grafia={n_g}, composto={n_c})")


if __name__ == "__main__":
    main()
