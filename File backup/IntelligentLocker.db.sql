BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "Lockers" (
	"locker_id"	INTEGER UNIQUE,
	"status"	TEXT DEFAULT 'Empty',
	"size"	text,
	"current_mssv" text unique
	PRIMARY KEY("locker_id")
);
CREATE TABLE IF NOT EXISTS "User" (
	"id"	INTEGER,
	"name"	TEXT NOT NULL,
	"mssv"	TEXT NOT NULL UNIQUE,
	"rfid_card"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);
INSERT INTO "Lockers" VALUES (1,'Empty','small
');
INSERT INTO "Lockers" VALUES (2,'Empty','small');
INSERT INTO "Lockers" VALUES (3,'Empty','small
');
INSERT INTO "Lockers" VALUES (4,'Empty','small
');
INSERT INTO "Lockers" VALUES (5,'Empty','small
');
INSERT INTO "Lockers" VALUES (6,'Empty','small
');
INSERT INTO "Lockers" VALUES (7,'Empty','small
');
INSERT INTO "Lockers" VALUES (8,'Empty','small
');
INSERT INTO "Lockers" VALUES (9,'Empty','small
');
INSERT INTO "Lockers" VALUES (10,'Empty','big');
INSERT INTO "Lockers" VALUES (11,'Empty','big');
INSERT INTO "Lockers" VALUES (12,'Empty','big');
INSERT INTO "Lockers" VALUES (13,'Empty','big');
INSERT INTO "Lockers" VALUES (14,'Empty','big');
INSERT INTO "Lockers" VALUES (15,'Empty','big');
INSERT INTO "User" VALUES (1,'Nguyen Duy Truong','22146436','123456');
INSERT INTO "User" VALUES (2,'Dang Huu Kien','22146337','234567');
INSERT INTO "User" VALUES (3,'Ca Tan Duong','22146289','012345');
COMMIT;
