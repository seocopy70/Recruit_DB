const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.express = express;
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Database setup
const dbPath = path.join(__dirname, 'recruiting.db');
const db = new sqlite3.Database(dbPath, (err) => {
  if (err) {
    console.error('Database connection error:', err.message);
  } else {
    console.log('Connected to SQLite database.');
  }
});

// Create table if not exists
db.run(`CREATE TABLE IF NOT EXISTS candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  contact TEXT,
  contact_date TEXT,
  manager TEXT,
  status TEXT,
  result TEXT,
  memo TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)`, (err) => {
  if (err) {
    console.error('Error creating table:', err.message);
  } else {
    console.log('Candidates table ready.');
  }
});

// API Routes
// Get all candidates
app.get('/api/candidates', (req, res) => {
  const query = 'SELECT * FROM candidates ORDER BY created_at DESC';
  db.all(query, [], (err, rows) => {
    if (err) {
      res.status(500).json({ error: err.message });
      return;
    }
    res.json(rows);
  });
});

// Add candidate
app.post('/api/candidates', (req, res) => {
  const { name, contact, contact_date, manager, status, result, memo } = req.body;
    if (!name) {
      res.status(400).json({ error: '이름은 필수입니다.' });
      return;
    }
  const query = `INSERT INTO candidates (name, contact, contact_date, manager, status, result, memo) VALUES (?, ?, ?, ?, ?, ?, ?)`;
  const params = [name, contact, contact_date, manager, status, result, memo];
  
  db.run(query, params, function(err) {
    if (err) {
      res.status(500).json({ error: err.message });
      return;
    }
    res.json({
      id: this.lastID,
      message: '후보자가 성공적으로 등록되었습니다.'
    });
  });
});

// Update candidate
app.put('/api/candidates/:id', (req, res) => {
  const { name, contact, contact_date, manager, status, result, memo } = req.body;
  const { id } = req.params;
  
  const query = `UPDATE candidates SET name = ?, contact = ?, contact_date = ?, manager = ?, status = ?, result = ?, memo = ? WHERE id = ?`;
  const params = [name, contact, contact_date, manager, status, result, memo, id];
  
  db.run(query, params, function(err) {
    if (err) {
      res.status(500).json({ error: err.message });
      return;
    }
    res.json({ message: '후보자 정보가 수정되었습니다.', changes: this.changes });
  });
});

// Delete candidate
app.delete('/api/candidates/:id', (req, res) => {
  const { id } = req.params;
  const query = `DELETE FROM candidates WHERE id = ?`;
  
  db.run(query, [id], function(err) {
    if (err) {
      res.status(500).json({ error: err.message });
      return;
    }
    res.json({ message: '후보자가 삭제되었습니다.', changes: this.changes });
  });
});

app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`);
});