# Guide Configuration Google OAuth pour PAM

## 🚀 Étape 1: Accéder à Google Cloud Console
1. Allez sur https://console.cloud.google.com/
2. Connectez-vous avec votre compte Google

## 📋 Étape 2: Créer ou sélectionner un projet
1. Cliquez sur le menu déroulant du projet (en haut à gauche)
2. Cliquez sur "NOUVEAU PROJET" ou sélectionnez un projet existant
3. Donnez un nom à votre projet (ex: "PAM Calendar Integration")
4. Cliquez sur "CRÉER"

## 🔧 Étape 3: Activer l'API Google Calendar
1. Dans le menu de navigation (hamburger), allez à "APIs et services" → "Bibliothèque"
2. Recherchez "Google Calendar API"
3. Cliquez sur "Google Calendar API"
4. Cliquez sur "ACTIVER"

## 🔑 Étape 4: Créer les identifiants OAuth
1. Allez à "APIs et services" → "Identifiants"
2. Cliquez sur "+ CRÉER DES IDENTIFIANTS" → "ID client OAuth"
3. Si c'est la première fois, vous devrez configurer l'écran de consentement OAuth:

### Configuration de l'écran de consentement:
- **Type d'utilisateur**: Externe
- **Nom de l'application**: PAM Calendar Integration
- **E-mail de contact utilisateur**: votre email
- **Logo** (optionnel): vous pouvez passer
- **Domaine d'application**: localhost (pour dev)
- **Domaines autorisés**: `localhost`

### Création de l'ID client OAuth:
1. **Type d'application**: Application Web
2. **Nom**: PAM Calendar OAuth
3. **Origines JavaScript autorisées**:
   ```
   http://localhost:3000
   http://localhost:8000
   ```
4. **URI de redirection autorisés**:
   ```
   http://localhost:8000/integrations/oauth/google_calendar/callback
   ```
5. Cliquez sur "CRÉER"

## 📝 Étape 5: Récupérer les identifiants
Après création, vous obtenez:
- **ID client** (commence par quelque chose comme `123456789-abc...googleusercontent.com`)
- **Code secret du client** (chaîne aléatoire)

## ⚙️ Étape 6: Mettre à jour votre .env
```bash
# Remplacez ces valeurs dans votre fichier .env
GOOGLE_CLIENT_ID=votre_client_id_ici
GOOGLE_CLIENT_SECRET=votre_client_secret_ici
```

## 🔐 Étape 7: Générer une clé de chiffrement
```bash
# Dans le terminal, générez une clé de chiffrement:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Ajoutez cette clé à votre .env:
```bash
PAM_CREDENTIAL_ENCRYPTION_KEY=votre_clé_générée_ici
```

## 🧪 Étape 8: Tester la configuration
```bash
cd MARK_I/backend_python/api
python test_calendar_setup.py
```

## 📋 URLs importantes à retenir:
- **OAuth Consent Screen**: https://console.cloud.google.com/apis/credentials/consent
- **Credentials**: https://console.cloud.google.com/apis/credentials
- **Calendar API**: https://console.cloud.google.com/apis/library/calendar.googleapis.com

## ⚠️ Notes importantes:
1. Pour la production, vous devrez configurer des domaines réels
2. L'écran de consentement peut rester en mode "Test" pour le développement
3. En mode test, seuls les utilisateurs ajoutés manuellement peuvent se connecter
4. Pour publier l'app, vous devrez passer par la vérification Google

## 🔄 Prochaines étapes après configuration:
1. Redémarrer votre serveur FastAPI
2. Tester le flow OAuth via l'API
3. Intégrer dans l'interface utilisateur PAM 