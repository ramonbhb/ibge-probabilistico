import re
import unicodedata

def fonetica(nome):
    
    nome = limpar(nome)
    
    # Trata cedilha e ñ antes de remover acentos (agora em MAIÚSCULO)
    nome = nome.replace('Ç', 'SS')
    nome = nome.replace('Ñ', 'NH')
    
    # Remove acentos (converte para ASCII puro)
    nome = unicodedata.normalize('NFKD', nome).encode('ASCII', 'ignore').decode('utf-8')
    
    # --- NOVA REGRA: REMOÇÃO DE CARACTERES ESPECIAIS ---
    # 1. Troca hifens e underlines por espaço (MARIA-CLARA -> MARIA CLARA)
    nome = re.sub(r'[-_]', ' ', nome)
    # 2. Remove tudo que NÃO for letra de 'A' a 'Z' ou espaço em branco
    nome = re.sub(r'[^A-Z\s]', '', nome)
    
    partes = nome.split()
    resultado = []
    
    for p in partes:
        # --- REGRAS DE ESTRANGEIRISMO E DÍGRAFOS ---
        p = re.sub(r'Y', 'I', p)
        p = re.sub(r'SCH(?![AEIOU])', 'XI', p) 
        p = re.sub(r'SCH(?=[AEIOU])', 'X', p)
        p = re.sub(r'SH(?![AEIOU])', 'XI', p) 
        p = re.sub(r'SH(?=[AEIOU])', 'X', p)   
        p = re.sub(r'CH(?=[AEIOU])', 'X', p)
        p = re.sub(r'CH(?![AEIOU])', 'K', p)  
        p = re.sub(r'PH', 'F', p)
        p = re.sub(r'PT', 'T', p)
        p = re.sub(r'ICT', 'IT', p)
        p = re.sub(r'CK', 'K', p)    
        p = re.sub(r'QU', 'K', p) 
        p = re.sub(r'G(?=[BCDFGHJKLMNPQRSTVWXYZÇ])', 'GUI', p)   

        # --- REGRAS DO W ---
        # W seguido de A ou L geralmente tem som de V (Wagner, Walter, Wladimir)
        p = re.sub(r'W(?=[AL])', 'V', p)
        # W seguido de E, I ou O geralmente tem som de U (Wesley, William, Washington)
        p = re.sub(r'W(?=[EIO])', 'U', p)
        # Qualquer outro W que sobrar vira U por padrão
        p = re.sub(r'W', 'U', p)
        
        # --- NASALIZAÇÃO UNIVERSAL ---
        p = re.sub(r'M([BCDFGHJKLMNPQRSTVWXZ])', r'N\1', p)
        
        # --- REGRAS DO C, G, S, Z ---
        p = re.sub(r'(?<!N)H', '', p)
        p = re.sub(r'([AEIOU])S([AEIOU])', r'\1Z\2', p)                  
        p = re.sub(r'C([EI])', r'S\1', p)        
        p = re.sub(r'C', 'K', p)                 
        p = re.sub(r'G([EI])', r'J\1', p)        
          
        

        # --- LETRAS REPETIDAS ---
        p = re.sub(r'(.)\1+', r'\1', p)         

         # --- REGRAS DE FINAL DE PALAVRA ---
        p = re.sub(r'O$', 'U', p)    
        p = re.sub(r'OS$', 'US', p) 
        p = re.sub(r'E$', 'I', p)    
        p = re.sub(r'ES$', 'IS', p)  
        p = re.sub(r'Z$', 'S', p)    
        p = re.sub(r'M$', 'N', p)    
        p = re.sub(r'D$', '', p)
        
        # --- REGRAS DE "I" EPENTÉTICO ---
        p = re.sub(r'^S([BCDFGHJKLMNPQRSTVWXZ])', r'IS\1', p)
        p = re.sub(r'([BDPTKVGF])([BDPTKVGMNC])', r'\1I\2', p)
        p = re.sub(r'([BCDFGJKPTVXZ])$', r'\1I', p)

        p = re.sub(r'(?<=[AEIO])L(?=[BCDFGHJKLMNPQRSTVWXYZÇ]|$)', 'U', p) 
        #p = re.sub(r'(?<=[BCDFGHJKLMNPQRSTVWXYZÇ])E(?=[BCDFGHJKLPQTVWYÇ])', 'I', p)
        
       
        
        
        
        if p: # Evita adicionar strings vazias caso a palavra fosse só pontuação
            resultado.append(p)
        
    return " ".join(resultado)

def limpar(texto):
    if not isinstance(texto, str):
        return ""
        
    # Converte tudo para maiúsculo no primeiro momento possível
    texto = texto.upper()
        
    # Lista dos conectivos, artigos e preposições (agora em MAIÚSCULO)
    conectivos = {
        "DA", "DE", "DI", "DO", "DU", "DAS", "DOS", "DES", "DEL", "E", "Y"
    }

    # 2. Dividir o texto em palavras
    palavras = texto.split()

    # 3. Filtrar removendo os conectivos
    palavras_filtradas = [palavra for palavra in palavras if palavra not in conectivos]

    # 4. Juntar novamente em uma string
    return " ".join(palavras_filtradas)