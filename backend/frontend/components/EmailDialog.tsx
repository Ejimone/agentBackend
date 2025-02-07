import React, { useState } from 'react';
import { Dialog, TextField, Button, Typography, Box } from '@mui/material';

interface EmailDialogProps {
  open: boolean;
  onClose: () => void;
  initialContent?: string;
}

export const EmailDialog: React.FC<EmailDialogProps> = ({ open, onClose, initialContent }) => {
  const [email, setEmail] = useState({
    to: '',
    subject: '',
    content: initialContent || '',
  });

  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  const handleSend = async () => {
    try {
      setSending(true);
      setError('');

      const response = await fetch('/api/send-email', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(email),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || 'Failed to send email');
      }

      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <Box sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>
          Compose Email
        </Typography>

        <TextField
          fullWidth
          label="To"
          value={email.to}
          onChange={(e) => setEmail({ ...email, to: e.target.value })}
          margin="normal"
          type="email"
        />

        <TextField
          fullWidth
          label="Subject"
          value={email.subject}
          onChange={(e) => setEmail({ ...email, subject: e.target.value })}
          margin="normal"
        />

        <TextField
          fullWidth
          label="Content"
          value={email.content}
          onChange={(e) => setEmail({ ...email, content: e.target.value })}
          margin="normal"
          multiline
          rows={8}
        />

        {error && (
          <Typography color="error" sx={{ mt: 2 }}>
            {error}
          </Typography>
        )}

        <Box sx={{ mt: 3, display: 'flex', justifyContent: 'flex-end', gap: 2 }}>
          <Button onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleSend}
            disabled={sending}
          >
            {sending ? 'Sending...' : 'Send Email'}
          </Button>
        </Box>
      </Box>
    </Dialog>
  );
}; 