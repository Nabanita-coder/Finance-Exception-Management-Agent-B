import os
import sys

# Add parent directory to sys.path so dbConnection can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dbConnection.db import engine, text

def migrate():
    with engine.connect() as conn:
        cols = [r[0] for r in conn.execute(text("DESCRIBE owners")).fetchall()]
        print("Existing columns:", cols)
        
        if "department" not in cols:
            conn.execute(text("ALTER TABLE owners ADD COLUMN department VARCHAR(100) DEFAULT 'General Finance'"))
            print("Added column: department")
            
        if "is_active" not in cols:
            conn.execute(text("ALTER TABLE owners ADD COLUMN is_active TINYINT DEFAULT 1"))
            print("Added column: is_active")
            
        if "max_approval_limit" not in cols:
            conn.execute(text("ALTER TABLE owners ADD COLUMN max_approval_limit FLOAT DEFAULT 1000000.0"))
            print("Added column: max_approval_limit")
            
        conn.commit()

        # Update existing owners with department specializations
        conn.execute(text("UPDATE owners SET department = 'DevOps' WHERE id = 1 AND (department IS NULL OR department = 'General Finance')"))
        conn.execute(text("UPDATE owners SET department = 'Sales' WHERE id = 2 AND (department IS NULL OR department = 'General Finance')"))
        conn.execute(text("UPDATE owners SET department = 'Marketing' WHERE id = 3 AND (department IS NULL OR department = 'General Finance')"))
        conn.execute(text("UPDATE owners SET department = 'All' WHERE id = 4 AND (department IS NULL OR department = 'General Finance')"))
        
        # Add additional department FP&A leads if they don't exist yet
        extra_owners = [
            (5, "DevOps Lead", "devops_finance@company.com", "Senior Finance Manager", 3, "DevOps", 1, 1500000.0),
            (6, "Sales FP&A Lead", "sales_finance@company.com", "Finance Manager", 2, "Sales", 1, 800000.0),
            (7, "Marketing Controller", "marketing_finance@company.com", "Senior Finance Manager", 3, "Marketing", 1, 1200000.0),
            (8, "General Ops Analyst", "ops_analyst@company.com", "Finance Executive", 1, "General Finance", 1, 300000.0)
        ]
        
        for o in extra_owners:
            conn.execute(text("""
                INSERT IGNORE INTO owners (id, name, email, role, level, department, is_active, max_approval_limit)
                VALUES (:id, :name, :email, :role, :level, :department, :is_active, :limit)
            """), {
                "id": o[0], "name": o[1], "email": o[2], "role": o[3],
                "level": o[4], "department": o[5], "is_active": o[6], "limit": o[7]
            })
        conn.commit()

        # Print current owners
        all_owners = conn.execute(text("SELECT id, name, role, level, department, is_active FROM owners")).fetchall()
        print("\nCurrent owners in database:")
        for row in all_owners:
            print(row)

if __name__ == "__main__":
    migrate()
