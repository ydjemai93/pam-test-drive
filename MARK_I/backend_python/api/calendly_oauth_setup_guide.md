# 📅 Calendly OAuth Setup Guide

## Step 1: Create Calendly Developer Account

1. Go to [Calendly Developer Portal](https://developer.calendly.com/)
2. Click **"Sign Up"** in the top-right corner
3. Sign up using your **GitHub** or **Google** account
   - ⚠️ **Note**: This is a separate developer account, not your regular Calendly user account

## Step 2: Create OAuth Application

1. After signing up, you'll be in the developer dashboard
2. Click **"Create a new OAuth application"**
3. Fill in the application details:

   **Application Name**: `PAM Agent Integration`
   
   **Application Type**: `Web Application`
   
   **Environment**: 
   - Choose **"Sandbox"** for development/testing
   - Use **"Production"** when ready for live users
   
   **Redirect URI**: `http://localhost:8000/integrations/oauth/calendly/callback`

4. Click **"Create Application"**

## Step 3: Copy OAuth Credentials

⚠️ **IMPORTANT**: Copy these values immediately - you won't be able to see the Client Secret again!

1. **Client ID**: Copy this value
2. **Client Secret**: Copy this value  
3. **Webhook Signing Key**: You can ignore this for now

## Step 4: Update Environment Variables

Edit `MARK_I/backend_python/api/.env` and replace the placeholders:

```env
# Replace these values with your real Calendly credentials
CALENDLY_CLIENT_ID=your_actual_client_id_here
CALENDLY_CLIENT_SECRET=your_actual_client_secret_here
```

## Step 5: Restart Backend Server

```bash
cd MARK_I/backend_python/api
python main.py
```

## Step 6: Test the Integration

1. Go to your PAM dashboard
2. Navigate to **Integrations** or **App Marketplace**
3. Find **Calendly** in the list
4. Click **"Connect"**
5. You should see the Calendly OAuth popup

## 🔧 Available Calendly Actions

Once connected, your pathway agents can use these Calendly actions:

- **`list_events`** - Get scheduled events
- **`get_user`** - Get current user info
- **`check_availability`** - Check availability windows
- **`cancel_event`** - Cancel scheduled events
- **`get_event_details`** - Get details of specific events
- **`list_event_types`** - Get available event types

## 🔒 Special Notes About Calendly OAuth

- **No Scopes Required**: Calendly OAuth automatically grants API access based on the user's account permissions
- **Token Expiry**: Access tokens expire after 2 hours
- **Refresh Tokens**: Automatically handled by PAM backend
- **Sandbox vs Production**: Use Sandbox for development, Production for live users

## 🚨 Troubleshooting

**Issue**: OAuth popup shows "Invalid Client ID"
**Solution**: Double-check that you copied the Client ID correctly and updated the `.env` file

**Issue**: "Redirect URI mismatch"  
**Solution**: Ensure the redirect URI in Calendly app matches exactly: `http://localhost:8000/integrations/oauth/calendly/callback`

**Issue**: OAuth works but API calls fail
**Solution**: Check if you're using the correct environment (Sandbox vs Production) and that your Calendly account has the necessary permissions

## 📖 Calendly API Documentation

- [Calendly Developer Docs](https://developer.calendly.com/)
- [OAuth Guide](https://developer.calendly.com/how-to-access-calendly-data-on-behalf-of-authenticated-users)
- [API Reference](https://calendly.stoplight.io/)

---

✅ **Ready!** Calendly is now available as an integration option in your PAM system! 