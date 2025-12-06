import config
import os
import time
from datetime import datetime
import uuid

# --- INITIALIZATION ---
db_client = None
db_local = None

if config.DB_MODE == 'FIREBASE':
    import firebase_admin
    from firebase_admin import credentials, firestore # <--- Import here is crucial
    
    if not firebase_admin._apps:
        cred_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()
            
    db_client = firestore.client()
    print("Firebase Firestore Connected (Permanent Storage)")

elif config.DB_MODE == 'LOCAL':
    from tinydb import TinyDB, Query
    db_local = TinyDB(config.LOCAL_DB_FILE, indent=4, separators=(',', ': '))
    print(f"Local Database Connected: {config.LOCAL_DB_FILE}")

class DBManager:
    """
    Manages database interactions for both Local (TinyDB) and Firebase modes.
    Handles Users, Portfolio, Watchlist, History, and Chat data persistence.
    """
    
    @staticmethod
    def get_timestamp():
        if config.DB_MODE == 'FIREBASE':
            return firestore.SERVER_TIMESTAMP
        return datetime.now().isoformat()

    # --- USER ---
    def get_user(self, user_id):
        """
        Retrieves user data by ID.
        
        Args:
            user_id (str): The unique identifier for the user.
            
        Returns:
            dict: User data if found, else None.
        """
        if config.DB_MODE == 'FIREBASE':
            doc = db_client.collection('users').document(user_id).get()
            return doc.to_dict() if doc.exists else None
        else:
            User = Query()
            res = db_local.table('users').search(User.id == user_id)
            return res[0] if res else None

    def create_or_update_user(self, user_id, data):
        if config.DB_MODE == 'FIREBASE':
            db_client.collection('users').document(user_id).set(data, merge=True)
            return data
        else:
            data['id'] = user_id
            table = db_local.table('users')
            User = Query()
            if table.search(User.id == user_id):
                table.update(data, User.id == user_id)
                return table.search(User.id == user_id)[0]
            else:
                table.insert(data)
                return data

    def update_user_cash(self, user_id, cash_amount):
        """
        Updates the cash balance for a user.
        
        Args:
            user_id (str): The unique identifier for the user.
            cash_amount (float): The new cash balance.
        """
        if config.DB_MODE == 'FIREBASE':
            db_client.collection('users').document(user_id).update({'cash': float(cash_amount)})
        else:
            User = Query()
            db_local.table('users').update({'cash': float(cash_amount)}, User.id == user_id)

    # --- TOKENS (The Critical Fix) ---
    def update_user_tokens(self, user_id, input_count, output_count):
        total = input_count + output_count
        
        if config.DB_MODE == 'FIREBASE':
            try:
                ref = db_client.collection('users').document(user_id)
                # Use .set with merge=True to prevent crashes if field is missing
                ref.set({
                    'token_usage': {
                        'input': firestore.Increment(input_count),
                        'output': firestore.Increment(output_count),
                        'total': firestore.Increment(total)
                    }
                }, merge=True)
            except Exception as e:
                print(f"Token Save Error: {e}")
        else:
            # LOCAL MODE logic
            User = Query()
            table = db_local.table('users')
            results = table.search(User.id == user_id)
            if results:
                user = results[0]
                current = user.get('token_usage', {'input': 0, 'output': 0, 'total': 0})
                new_usage = {
                    'input': current.get('input', 0) + input_count,
                    'output': current.get('output', 0) + output_count,
                    'total': current.get('total', 0) + total
                }
                table.update({'token_usage': new_usage}, User.id == user_id)

    # --- PORTFOLIO ---
    def get_portfolio_holdings(self, user_id):
        """
        Retrieves all portfolio holdings for a user.
        
        Args:
            user_id (str): The unique identifier for the user.
            
        Returns:
            dict: A dictionary of holdings keyed by ticker symbol.
        """
        if config.DB_MODE == 'FIREBASE':
            docs = db_client.collection(f'users/{user_id}/portfolio').stream()
            return {doc.id: doc.to_dict() for doc in docs}
        else:
            Portfolio = Query()
            items = db_local.table('portfolio').search(Portfolio.user_id == user_id)
            return {item['ticker']: item for item in items}

    def update_holding(self, user_id, ticker, data):
        if config.DB_MODE == 'FIREBASE':
            db_client.collection(f'users/{user_id}/portfolio').document(ticker).set(data, merge=True)
        else:
            table = db_local.table('portfolio')
            Portfolio = Query()
            data['user_id'] = user_id
            data['ticker'] = ticker
            if table.contains((Portfolio.user_id == user_id) & (Portfolio.ticker == ticker)):
                table.update(data, (Portfolio.user_id == user_id) & (Portfolio.ticker == ticker))
            else:
                table.insert(data)

    def delete_holding(self, user_id, ticker):
        if config.DB_MODE == 'FIREBASE':
            db_client.collection(f'users/{user_id}/portfolio').document(ticker).delete()
        else:
            Portfolio = Query()
            db_local.table('portfolio').remove((Portfolio.user_id == user_id) & (Portfolio.ticker == ticker))

    def reset_portfolio(self, user_id, cash_balance):
        if config.DB_MODE == 'FIREBASE':
            coll = db_client.collection(f'users/{user_id}/portfolio')
            for doc in coll.stream(): doc.reference.delete()
            db_client.collection('users').document(user_id).update({'cash': cash_balance})
        else:
            Portfolio = Query()
            db_local.table('portfolio').remove(Portfolio.user_id == user_id)
            self.update_user_cash(user_id, cash_balance)

    # --- WATCHLIST ---
    def get_watchlist(self, user_id):
        if config.DB_MODE == 'FIREBASE':
            docs = db_client.collection(f'users/{user_id}/watchlist').stream()
            return [doc.id for doc in docs]
        else:
            Watch = Query()
            items = db_local.table('watchlist').search(Watch.user_id == user_id)
            return [item['ticker'] for item in items]

    def add_to_watchlist(self, user_id, ticker):
        if config.DB_MODE == 'FIREBASE':
            db_client.collection(f'users/{user_id}/watchlist').document(ticker).set({'added_at': self.get_timestamp()})
        else:
            table = db_local.table('watchlist')
            Watch = Query()
            if not table.contains((Watch.user_id == user_id) & (Watch.ticker == ticker)):
                table.insert({'user_id': user_id, 'ticker': ticker, 'added_at': self.get_timestamp()})

    def remove_from_watchlist(self, user_id, ticker):
        if config.DB_MODE == 'FIREBASE':
            db_client.collection(f'users/{user_id}/watchlist').document(ticker).delete()
            return True
        else:
            Watch = Query()
            return db_local.table('watchlist').remove((Watch.user_id == user_id) & (Watch.ticker == ticker))

    # --- HISTORY ---
    def add_history_entry(self, user_id, entry_data):
        entry_data['timestamp'] = self.get_timestamp()
        if config.DB_MODE == 'FIREBASE':
            db_client.collection(f'users/{user_id}/history').add(entry_data)
        else:
            entry_data['user_id'] = user_id
            entry_data['timestamp'] = datetime.now().isoformat()
            db_local.table('history').insert(entry_data)

    def get_history(self, user_id, limit=15):
        if config.DB_MODE == 'FIREBASE':
            docs = db_client.collection(f'users/{user_id}/history').order_by('timestamp', direction='DESCENDING').limit(limit).stream()
            return [doc.to_dict() for doc in docs]
        else:
            Hist = Query()
            items = db_local.table('history').search(Hist.user_id == user_id)
            items.sort(key=lambda x: x['timestamp'], reverse=True)
            return items[:limit]

    # --- CHATS ---
    def create_chat(self, user_id, title, first_msg_text, first_msg_role='user'):
        timestamp = self.get_timestamp()
        if config.DB_MODE == 'FIREBASE':
            chat_ref = db_client.collection(f'users/{user_id}/chats').document()
            chat_id = chat_ref.id
            # Atomic Write (Batch)
            batch = db_client.batch()
            batch.set(chat_ref, {"title": title, "timestamp": timestamp})
            msg_ref = chat_ref.collection('messages').document()
            batch.set(msg_ref, {"role": first_msg_role, "text": first_msg_text, "timestamp": timestamp})
            batch.commit()
            return chat_id
        else:
            chat_id = str(uuid.uuid4())[:8]
            ts_iso = datetime.now().isoformat()
            db_local.table('chats').insert({'id': chat_id, 'user_id': user_id, 'title': title, 'timestamp': ts_iso})
            db_local.table('messages').insert({'chat_id': chat_id, 'user_id': user_id, 'role': first_msg_role, 'text': first_msg_text, 'timestamp': ts_iso})
            return chat_id

    def add_message(self, user_id, chat_id, role, text):
        timestamp = self.get_timestamp()
        if config.DB_MODE == 'FIREBASE':
            db_client.collection(f'users/{user_id}/chats/{chat_id}/messages').add({"role": role, "text": text, "timestamp": timestamp})
        else:
            db_local.table('messages').insert({'chat_id': chat_id, 'user_id': user_id, 'role': role, 'text': text, 'timestamp': datetime.now().isoformat()})

    def get_chats(self, user_id):
        if config.DB_MODE == 'FIREBASE':
            docs = db_client.collection(f'users/{user_id}/chats').order_by('timestamp', direction='DESCENDING').limit(50).stream()
            return [{"chatId": d.id, "title": d.to_dict().get("title", "Chat")} for d in docs]
        else:
            Chat = Query()
            items = db_local.table('chats').search(Chat.user_id == user_id)
            items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            return [{"chatId": d['id'], "title": d.get('title', 'Chat')} for d in items]

    def get_chat_messages(self, user_id, chat_id):
        if config.DB_MODE == 'FIREBASE':
            docs = db_client.collection(f'users/{user_id}/chats/{chat_id}/messages').order_by('timestamp', direction='ASCENDING').limit(100).stream()
            return [{"role": d.to_dict().get('role'), "text": d.to_dict().get('text')} for d in docs]
        else:
            Msg = Query()
            items = db_local.table('messages').search(Msg.chat_id == chat_id)
            items.sort(key=lambda x: x['timestamp'])
            return [{"role": d['role'], "text": d['text']} for d in items]

    def delete_chat(self, user_id, chat_id):
        if config.DB_MODE == 'FIREBASE':
            db_client.collection(f'users/{user_id}/chats').document(chat_id).delete()
        else:
            Chat, Msg = Query(), Query()
            db_local.table('chats').remove((Chat.id == chat_id) & (Chat.user_id == user_id))
            db_local.table('messages').remove(Msg.chat_id == chat_id)

    def rename_chat(self, user_id, chat_id, new_title):
        if config.DB_MODE == 'FIREBASE':
            db_client.collection(f'users/{user_id}/chats').document(chat_id).update({'title': new_title})
        else:
            Chat = Query()
            db_local.table('chats').update({'title': new_title}, (Chat.id == chat_id) & (Chat.user_id == user_id))