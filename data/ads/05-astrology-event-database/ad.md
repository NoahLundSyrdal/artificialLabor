Astrology Event Database & Interface
Open
Posted about 12 hours ago
•
Ends in 6 days
₹12500-37500 INR
Paid on delivery
I need a clean, portable database that records astrological event data—eclipses, planetary ingresses, retrogrades, you name it—and can be lifted straight into MySQL, . The core table structure should be normalized and come with keys, indexes, and a clear ERD so another hobbyist (or future-me) can understand it at a glance.

On top of that schema, build a simple HTML data-entry interface. Pure HTML/CSS with a dash of vanilla JavaScript is fine; no heavy frameworks. A small PHP helper for form handling is acceptable if it keeps things tidy, but the pages themselves have to load as plain HTML so they can live on any basic web host.

Inside the interface I’d like:
• A form to add, edit, and delete individual events (date, time, event type, brief notes).
• A lightweight search console where a user chooses an event type from a drop-down and instantly sees matching rows, ordered chronologically.

Export and portability matter just as much as the UI. Please include:
• An .sql file ready for import as well as a CSV dump.
• Brief “how-to” notes on moving the data to another engine (e.g., pg_dump / sqlite3 import).
• Any scripts used for seeding sample data.

I’ll consider it complete when the schema imports cleanly, the HTML pages talk to it seamlessly, and the search by type of astrological event returns accurate results without timeouts even on a modest shared host.
