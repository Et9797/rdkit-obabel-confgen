import io
import os
import sys
import shutil
import re
import zipfile
import requests
import logging
import traceback
import random
import time
import uuid
from openbabel import openbabel as ob
from openbabel import pybel
import confab 
from rdkit import Chem
from rdkit.Chem import AllChem
import conf_gen_rdkit
import pdbToSmileConverter
from flask import Flask, Response, render_template, request, redirect, url_for, send_file
from flask_mail import Mail, Message
from config import mail_username, mail_password

logging.basicConfig(filename="log.txt", level=logging.DEBUG, format='%(asctime)s %(message)s')

BASE_DIR = '/home/et/personal_projects/rdkit-obabel-confgen/'
MOLECULE_UPLOADS = '/home/et/personal_projects/rdkit-obabel-confgen/MOLECULE_UPLOADS/'
#change to '/var/www/html/rdkit-obabel-confgen/MOLECULE_UPLOADS/'

app = Flask(__name__)
app.config["BASE_DIR"] = BASE_DIR
app.config["MOLECULE_UPLOADS"] = MOLECULE_UPLOADS
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0 #don't cache the files
app.config["MAIL_SERVER"] = "smtp-mail.outlook.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USE_SSL"] = False
app.config["MAIL_USERNAME"] = mail_username
app.config["MAIL_PASSWORD"] = mail_password

mail = Mail(app)

@app.errorhandler(Exception)
def internal_error(exception):
    with open(os.path.join(app.config["BASE_DIR"], "error.log"), "a") as f:
        f.write(time.strftime("%d/%m %H:%M:%S") + "\n")
        exc_type, _ , _ = sys.exc_info()
        f.write(traceback.format_exc())
        f.write(f"{exc_type.__name__}" + "\n \n")
        if exc_type.__name__ == "ArgumentError":
            exc_type.__name__= "SMILES Parse Error"
    current_page = request.path.strip("/")
    return render_template(f"{current_page}.html", err=str(exc_type.__name__))


@app.route("/contact", methods=["POST","GET"])
def contact():
    if request.method == "POST":
        email = request.form["email"]
        message = request.form["message"].strip()
        msg = Message(subject="Conformer Webapp", body=f"Email: {email} \n \n{message}",
        sender=mail_username, recipients=[mail_username])
        mail.send(msg)
        return redirect(url_for("rdkit")) 
    

@app.route("/")
def index():
    return redirect(url_for("rdkit"))
    

@app.route("/rdkit")
def rdkit():
    return render_template("rdkit.html")


@app.route("/confab")
def confab_page():
    return render_template("confab.html")


@app.route("/reset/<method>/<job_id>")
def reset(method, job_id):
    if os.path.exists(os.path.join(app.config["MOLECULE_UPLOADS"], job_id)):
        shutil.rmtree(os.path.join(app.config["MOLECULE_UPLOADS"], job_id))
        if method == "confab":
            return redirect(url_for("confab_page"))
        else:
            return redirect(url_for("rdkit"))
    else:
        if method == "confab":
            return redirect(url_for("confab_page"))
        else:
            return redirect(url_for("rdkit"))


@app.route("/<method>/<job_id>") 
def serve_pdbs(method, job_id): 
    if os.path.exists(os.path.join(app.config["MOLECULE_UPLOADS"], job_id)):
        zipfolder = zipfile.ZipFile("Conformers.zip", "w", zipfile.ZIP_STORED)
        for f in os.listdir():
            if f != "Conformers.zip":
                zipfolder.write(f)
        zipfolder.close()
        zip_mem = io.BytesIO()
        with open(zipfolder.filename, "rb") as fo:
            zip_mem.write(fo.read())
            zip_mem.seek(0)
        fo.close()

        shutil.rmtree(os.path.join(app.config["MOLECULE_UPLOADS"], job_id))

        return send_file(zip_mem, mimetype="application/zip", as_attachment=True, 
        attachment_filename="Conformers.zip", cache_timeout=0)
    else:
        if method == "confab":
            return redirect(url_for("confab_page"))
        else:
            return redirect(url_for("rdkit"))


@app.route("/<method>", methods=["POST", "GET"])
def form_handler(method):
    if request.method == "POST":
        unique_id = str(uuid.uuid4())
        if method == "confab":
            force_field = request.form["force_field"]
        smiles = request.form["smiles_molecule"]
        pdb_file = request.files["pdb_molecule"]
        no_conformers = int(request.form["no_conformers"])
        with open(os.path.join(app.config["BASE_DIR"], "molecules.txt"), "a") as f:
            f.write(time.strftime("%d/%m %H:%M:%S") + "\n")
            f.write(f"\t \t Smiles: {smiles} \n")
            f.write(f"\t \t PDB: {pdb_file.filename} \n")
            f.write(f"\t \t N_conformers: {no_conformers} \n \n")
        if smiles:
            mol_path = os.path.join(app.config["MOLECULE_UPLOADS"], unique_id)
        else: #PDB was provided
            assert pdb_file.filename.split(".")[-1] == "pdb"
            pdb_temp_path = os.path.join(app.config["MOLECULE_UPLOADS"], pdb_file.filename)
            pdb_file.save(pdb_temp_path)
            smiles = pdbToSmileConverter.pdb_to_smiles(pdb_temp_path)
            mol_path = os.path.join(app.config["MOLECULE_UPLOADS"], unique_id)
            os.remove(pdb_temp_path)
            
        os.mkdir(mol_path)
        os.chdir(mol_path)

        if method == "confab":
            mole = confab.generate_conformers(smiles, force_field)
            if mole.NumConformers() > no_conformers:
                conf_sample = random.sample(range(mole.NumConformers()), no_conformers)
                confab.write_conformers(mole, conf_sample)
            else:
                confab.write_conformers(mole, range(mole.NumConformers()))
            return render_template("confab.html", method="confab", job_id=unique_id)
        else:
            conformers = conf_gen_rdkit.gen_conformers(smiles, no_conformers)
            conf_gen_rdkit.write_confs_to_pdb(conformers)
            return render_template("rdkit.html", method="rdkit", job_id=unique_id)
        

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)

