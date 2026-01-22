# make_admin.py
from db import SessionLocal
from models import User

# Put the email you used to sign up (admin/developer account)
EMAIL_TO_PROMOTE = "jeffdenver97@gmail.com"

def main():
    db = SessionLocal()
    try:
        email = EMAIL_TO_PROMOTE.strip().lower()
        user = db.query(User).filter(User.email == email).first()

        if not user:
            print("❌ No user found with that email.")
            return

        user.is_admin = True
        db.add(user)
        db.commit()

        print(f"✅ {user.email} is now an admin (is_admin=True).")
    finally:
        db.close()

if __name__ == "__main__":
    main()
