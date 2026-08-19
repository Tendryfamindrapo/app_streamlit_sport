"""NexaBudget — Streamlit. Lancez : streamlit run app.py"""
import json
import os
import sqlite3
from datetime import date
from pathlib import Path
import pandas as pd
import streamlit as st
import redis
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

DB=Path(__file__).with_name("nexabudget.db")
load_dotenv(Path(__file__).with_name(".env"))
REDIS_URL=os.getenv("REDIS_URL", "")
# Alternative pratique si le fournisseur Redis donne les paramètres séparément.
if not REDIS_URL and os.getenv("REDIS_HOST"):
 REDIS_URL="redis://:{password}@{host}:{port}/{database}".format(password=os.getenv("REDIS_PASSWORD",""),host=os.getenv("REDIS_HOST"),port=os.getenv("REDIS_PORT","6379"),database=os.getenv("REDIS_DB","0"))
cache=redis.Redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None
CATS={"Alimentation":"🛒","Transport":"🚗","Loisirs":"🎬","Logement":"🏠","Santé":"💚","Salaire":"💼","Autre":"◇"}
def db():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c
def redis_ready():
 try:return bool(cache and cache.ping())
 except redis.RedisError:return False
def storage_mode(): return "Redis" if redis_ready() else "SQLite (secours local)"
def setup():
 if redis_ready():
  if cache.exists("nexabudget:user:1"):return
  cache.hset("nexabudget:user:1",mapping={"id":"1","name":"Alex Martin","email":"alex@nexabudget.fr","password_hash":generate_password_hash("budget2026")})
  cache.set("nexabudget:user_email:alex@nexabudget.fr","1");cache.set("nexabudget:user_seq","1")
  x=[{"id":i+1,"user_id":1,"name":r[0],"category":r[1],"date":r[2],"amount":r[3],"type":r[4]}for i,r in enumerate([("Salaire — Nexa Studio","Salaire","2026-08-01",2800,"income"),("Loyer appartement","Logement","2026-08-03",850,"expense"),("Carrefour Market","Alimentation","2026-08-17",76.4,"expense"),("Netflix","Loisirs","2026-08-16",15.99,"expense"),("Station TotalEnergies","Transport","2026-08-15",58.2,"expense"),("Restaurant Le Petit Bistro","Loisirs","2026-08-13",38.5,"expense"),("Pharmacie Centrale","Santé","2026-08-11",22.9,"expense"),("Remboursement Emma","Autre","2026-08-08",45,"income")])]
  b=[{"id":i+1,"user_id":1,"name":n,"limit_amount":v}for i,(n,v)in enumerate([("Alimentation",350),("Transport",160),("Loisirs",180),("Logement",900),("Santé",100)])]
  cache.set("nexabudget:transactions:1",json.dumps(x));cache.set("nexabudget:budgets:1",json.dumps(b));return
 with db() as c:
  c.executescript("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,email TEXT UNIQUE,password_hash TEXT);CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,name TEXT,category TEXT,date TEXT,amount REAL,type TEXT);CREATE TABLE IF NOT EXISTS budgets(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,name TEXT,limit_amount REAL);")
  if c.execute("SELECT 1 FROM users WHERE email=?",("alex@nexabudget.fr",)).fetchone():return
  u=c.execute("INSERT INTO users VALUES(NULL,?,?,?)",("Alex Martin","alex@nexabudget.fr",generate_password_hash("budget2026"))).lastrowid
  x=[("Salaire — Nexa Studio","Salaire","2026-08-01",2800,"income"),("Loyer appartement","Logement","2026-08-03",850,"expense"),("Carrefour Market","Alimentation","2026-08-17",76.4,"expense"),("Netflix","Loisirs","2026-08-16",15.99,"expense"),("Station TotalEnergies","Transport","2026-08-15",58.2,"expense"),("Restaurant Le Petit Bistro","Loisirs","2026-08-13",38.5,"expense"),("Pharmacie Centrale","Santé","2026-08-11",22.9,"expense"),("Remboursement Emma","Autre","2026-08-08",45,"income")]
  c.executemany("INSERT INTO transactions(user_id,name,category,date,amount,type) VALUES(?,?,?,?,?,?)",[(u,*r)for r in x]);c.executemany("INSERT INTO budgets(user_id,name,limit_amount) VALUES(?,?,?)",[(u,*r)for r in [("Alimentation",350),("Transport",160),("Loisirs",180),("Logement",900),("Santé",100)]])
def euro(x):return f"{x:,.2f} €".replace(","," ").replace(".",",")
def tx(u):
 if redis_ready():
  rows=json.loads(cache.get(f"nexabudget:transactions:{u}") or "[]")
  return pd.DataFrame(rows,columns=["id","user_id","name","category","date","amount","type"]).sort_values(["date","id"],ascending=False)
 with db() as c:r=c.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY date DESC,id DESC",(u,)).fetchall()
 return pd.DataFrame(r,columns=["id","user_id","name","category","date","amount","type"])
def bd(u):
 if redis_ready():return json.loads(cache.get(f"nexabudget:budgets:{u}") or "[]")
 with db() as c:return[dict(r)for r in c.execute("SELECT * FROM budgets WHERE user_id=?",(u,))]
def save_transaction(u,n,cat,day,amount,kind):
 if redis_ready():
  rows=json.loads(cache.get(f"nexabudget:transactions:{u}") or "[]");rows.append({"id":max([x["id"]for x in rows],default=0)+1,"user_id":u,"name":n,"category":cat,"date":day,"amount":amount,"type":kind});cache.set(f"nexabudget:transactions:{u}",json.dumps(rows));return
 with db()as c:c.execute("INSERT INTO transactions(user_id,name,category,date,amount,type) VALUES(?,?,?,?,?,?)",(u,n,cat,day,amount,kind))
def current_balance(u):
 data=tx(u)
 if data.empty:return 0.0
 return float(data.loc[data.type=="income","amount"].sum()-data.loc[data.type=="expense","amount"].sum())
def save_budget(u,n,limit):
 if redis_ready():
  rows=json.loads(cache.get(f"nexabudget:budgets:{u}") or "[]");rows.append({"id":max([x["id"]for x in rows],default=0)+1,"user_id":u,"name":n,"limit_amount":limit});cache.set(f"nexabudget:budgets:{u}",json.dumps(rows));return
 with db()as c:c.execute("INSERT INTO budgets(user_id,name,limit_amount) VALUES(?,?,?)",(u,n,limit))
def find_user(email):
 if redis_ready():
  uid=cache.get(f"nexabudget:user_email:{email}")
  return cache.hgetall(f"nexabudget:user:{uid}") if uid else None
 with db()as c:return c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
def register_user(name,email,password,initial_budget):
 email=email.lower().strip()
 if find_user(email):return None,"Cette adresse e-mail est déjà utilisée."
 if redis_ready():
  uid=cache.incr("nexabudget:user_seq")
  cache.hset(f"nexabudget:user:{uid}",mapping={"id":uid,"name":name,"email":email,"password_hash":generate_password_hash(password)})
  cache.set(f"nexabudget:user_email:{email}",uid);cache.set(f"nexabudget:transactions:{uid}","[]");cache.set(f"nexabudget:budgets:{uid}","[]")
  if initial_budget>0:save_transaction(uid,"Budget initial","Autre",date.today().isoformat(),initial_budget,"income")
  return uid,None
 try:
  with db()as c:uid=c.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",(name,email,generate_password_hash(password))).lastrowid
  if initial_budget>0:save_transaction(uid,"Budget initial","Autre",date.today().isoformat(),initial_budget,"income")
  return uid,None
 except sqlite3.IntegrityError:return None,"Cette adresse e-mail est déjà utilisée."
def add(u):
 with st.expander("＋ Ajouter une transaction"):
  with st.form("new",clear_on_submit=True):
   n=st.text_input("Libellé",placeholder="Ex. Courses Carrefour");a,b=st.columns(2);amount=a.number_input("Montant (€)",.01,value=10.);kind=a.selectbox("Type",["Dépense","Revenu"]);cat=b.selectbox("Catégorie",list(CATS));day=b.date_input("Date",date.today())
   if st.form_submit_button("Enregistrer",type="primary",use_container_width=True):
    if not n.strip():st.warning("Ajoutez un libellé.")
    else:
     transaction_type="income"if kind=="Revenu"else"expense"
     balance=current_balance(u)
     if transaction_type=="expense" and amount>balance:
      st.error(f"Solde insuffisant : vous avez {euro(balance)}. Cette dépense de {euro(amount)} ferait passer votre compte dans le négatif.")
     else:
      save_transaction(u,n.strip(),cat,day.isoformat(),amount,transaction_type)
      st.rerun()
def show(data):
 if data.empty:st.info("Aucune transaction.");return
 x=data.copy();x["Catégorie"]=x.category.map(lambda n:f"{CATS.get(n,'◇')} {n}");x["Type"]=x.type.map({"income":"Revenu","expense":"Dépense"});x["Montant"]=x.apply(lambda r:("+ "if r.type=="income"else"− ")+euro(r.amount),axis=1);x=x.rename(columns={"name":"Transaction","date":"Date"});st.dataframe(x[["Transaction","Catégorie","Date","Type","Montant"]],hide_index=True,use_container_width=True)
def home(u):
 data=tx(u);ex=data[data.type=="expense"];inc=data[data.type=="income"];i,e=inc.amount.sum(),ex.amount.sum();bal=i-e
 st.title(f"Bonjour, {st.session_state.name} 👋");st.caption("Voici le résumé de vos finances aujourd’hui.");add(u);a,b,c,d=st.columns(4);a.metric("Solde total",euro(bal),"+8,2 %");b.metric("Revenus",euro(i),"+4,6 %");c.metric("Dépenses",euro(e),"−12,1 %",delta_color="inverse");d.metric("Épargne",euro(max(0,bal)),"Objectif : 2 000 €")
 st.divider();a,b=st.columns([1.65,1])
 with a:
  st.subheader("Flux de trésorerie")
  if data.empty:
   st.info("Ajoutez des transactions pour afficher le flux de trésorerie.")
  else:
   p=data.copy();p.date=pd.to_datetime(p.date)
   chart_data=p.pivot_table(index="date",columns="type",values="amount",aggfunc="sum",fill_value=0).rename(columns={"income":"Revenus","expense":"Dépenses"})
   # Une couleur par série : le graphique reste valide avec 1 seul type de mouvement.
   st.line_chart(chart_data,color=["#7467ed","#f17a71"][:len(chart_data.columns)])
 with b:
  st.subheader("Vos budgets")
  for z in bd(u):
   used=ex.loc[ex.category==z["name"],"amount"].sum();st.write(f"{CATS.get(z['name'],'◇')} **{z['name']}**");st.caption(f"{euro(used)} sur {euro(z['limit_amount'])}");st.progress(min(used/z["limit_amount"],1.0))
 st.subheader("Dernières transactions");show(data.head(6))
def all_tx(u):
 st.title("Transactions");st.caption("Gérez toutes vos entrées et sorties d’argent.");add(u);x=tx(u);a,b,c=st.columns([2,1,1]);q=a.text_input("Rechercher");cat=b.selectbox("Catégorie",["Toutes"]+list(CATS));kind=c.selectbox("Type",["Tous","Dépenses","Revenus"])
 if q:x=x[x.name.str.contains(q,case=False,na=False)|x.category.str.contains(q,case=False,na=False)]
 if cat!="Toutes":x=x[x.category==cat]
 if kind!="Tous":x=x[x.type==("expense"if kind=="Dépenses"else"income")]
 show(x)
def budget(u):
 st.title("Budgets mensuels");st.caption("Gardez vos dépenses sous contrôle.")
 with st.expander("＋ Créer un budget"):
  with st.form("budget"):
   n=st.selectbox("Catégorie",[x for x in CATS if x!="Salaire"]);l=st.number_input("Montant maximum (€)",1.,value=100.)
   if st.form_submit_button("Créer",type="primary"):
    save_budget(u,n,l)
    st.rerun()
 ex=tx(u).query("type=='expense'");cols=st.columns(3)
 for j,z in enumerate(bd(u)):
  used=ex.loc[ex.category==z["name"],"amount"].sum()
  with cols[j%3]:st.subheader(f"{CATS.get(z['name'],'◇')} {z['name']}");st.write(f"**{euro(used)}** sur {euro(z['limit_amount'])}");st.progress(min(used/z["limit_amount"],1));st.caption(f"{euro(max(0,z['limit_amount']-used))} restant")
def stats(u):
 st.title("Statistiques");x=tx(u).query("type=='expense'")
 if x.empty:st.info("Ajoutez une dépense pour voir vos statistiques.");return
 t=x.groupby("category",as_index=False).amount.sum().sort_values("amount",ascending=False);a,b=st.columns([1.3,1])
 with a:st.subheader("Dépenses par catégorie");st.bar_chart(t.set_index("category"),color="#7467ed")
 with b:st.subheader("Répartition");st.dataframe(t.rename(columns={"category":"Catégorie","amount":"Montant"}),hide_index=True,use_container_width=True);st.success("Vos dépenses sont sous contrôle !")
def login():
 _,m,_=st.columns([1,1.3,1])
 with m:
  st.title("💳 NexaBudget");st.caption("VOTRE ARGENT, EN CLAIR");st.subheader("Content de vous revoir !")
  signin,signup=st.tabs(["Connexion","Créer un compte"])
  with signin:
   with st.form("login"):
    mail=st.text_input("Adresse e-mail",value="alex@nexabudget.fr");pw=st.text_input("Mot de passe",value="budget2026",type="password");ok=st.form_submit_button("Se connecter",type="primary",use_container_width=True)
   if ok:
    r=find_user(mail.lower().strip())
    if r and check_password_hash(r["password_hash"],pw):st.session_state.uid=int(r["id"]);st.session_state.name=r["name"];st.rerun()
    st.error("Adresse e-mail ou mot de passe incorrect.")
   st.info("Démo : alex@nexabudget.fr / budget2026")
  with signup:
   st.write("Créez votre espace NexaBudget gratuitement.")
   with st.form("signup",clear_on_submit=True):
    name=st.text_input("Nom complet");email=st.text_input("Adresse e-mail",key="signup_email");initial_budget=st.number_input("Budget initial disponible (€)",min_value=0.0,value=0.0,step=10.0,help="Ce montant devient votre solde de départ. Les dépenses ne pourront pas le dépasser.");password=st.text_input("Mot de passe",type="password",key="signup_password");confirm=st.text_input("Confirmer le mot de passe",type="password")
    create=st.form_submit_button("Créer mon compte",type="primary",use_container_width=True)
   if create:
    if not name.strip() or not email.strip() or not password:st.warning("Tous les champs sont obligatoires.")
    elif "@" not in email:st.warning("Saisissez une adresse e-mail valide.")
    elif len(password)<8:st.warning("Le mot de passe doit contenir au moins 8 caractères.")
    elif password!=confirm:st.warning("Les mots de passe ne correspondent pas.")
    else:
     uid,error=register_user(name.strip(),email,password,initial_budget)
     if error:st.error(error)
     else:st.session_state.uid=int(uid);st.session_state.name=name.strip();st.success("Compte créé avec succès !");st.rerun()
def styles(dark):
 bg,card,text,muted,border=("#171526","#24213c","#f5f3ff","#bcb7d0","#393651") if dark else ("#f7f6fb","#ffffff","#24213c","#756f87","#e6e4ee")
 st.markdown(f"""<style>:root{{--bg:{bg};--card:{card};--text:{text};--muted:{muted};--border:{border};}}.stApp,[data-testid='stAppViewContainer'],[data-testid='stMain']{{background:var(--bg)!important;color:var(--text)!important}}[data-testid='stSidebar']{{background:#28204a!important}}[data-testid='stSidebar'] *{{color:#fff!important}}h1,h2,h3,p,label,[data-testid='stMarkdownContainer'],[data-testid='stCaptionContainer']{{color:var(--text)!important}}[data-testid='stCaptionContainer']{{color:var(--muted)!important}}div[data-testid='stMetric'],[data-testid='stDataFrame'],[data-testid='stExpander']{{background:var(--card)!important;border:1px solid var(--border)!important;border-radius:12px;padding:15px}}input,select,[data-baseweb='select']>div{{background:var(--card)!important;color:var(--text)!important}} </style>""",unsafe_allow_html=True)
def main():
 st.set_page_config("NexaBudget","💳",layout="wide");setup();styles(st.session_state.get("dark",False))
 if"uid"not in st.session_state:login();return
 with st.sidebar:
  st.title("NexaBudget");st.caption("VOTRE ARGENT, EN CLAIR");p=st.radio("Navigation",["Tableau de bord","Transactions","Budgets","Statistiques"],label_visibility="collapsed");st.toggle("Mode sombre",key="dark");st.caption(f"Base active : {storage_mode()}");st.divider();st.write(f"👤 **{st.session_state.name}**")
  if st.button("Déconnexion",use_container_width=True):st.session_state.clear();st.rerun()
 {"Tableau de bord":home,"Transactions":all_tx,"Budgets":budget,"Statistiques":stats}[p](st.session_state.uid)
if __name__=="__main__":main()
