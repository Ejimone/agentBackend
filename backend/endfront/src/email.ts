// here, emails will be handled, this will be calling sendemail function, this will be like a pop up, whcih will be activated the user gives the agent an email prompt, as seen in agent.py
// however, this will be ui, the ui should be smooth, the user will also be able to edit the email before sending it

import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/use-toast";
import { Switch } from "@/components/ui/switch";

interface EmailFormData {
  to: string;
  subject: string;
  body: string;
  senderName: string;
  receiverName: string;
}

export function EmailDialog() {
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [useAI, setUseAI] = useState(false);
  const [formData, setFormData] = useState<EmailFormData>({
    to: '',
    subject: '',
    body: '',
    senderName: '',
    receiverName: ''
  });

  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const validateEmail = (email: string) => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateEmail(formData.to)) {
      toast({
        title: "Invalid Email",
        description: "Please enter a valid email address",
        variant: "destructive"
      });
      return;
    }

    if (!formData.subject || !formData.body) {
      toast({
        title: "Missing Fields",
        description: "Please fill in all required fields",
        variant: "destructive"
      });
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch('/api/send-email', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      const data = await response.json();

      if (data.status === 'success') {
        toast({
          title: "Success",
          description: "Email sent successfully!",
        });
        setIsOpen(false);
        setFormData({
          to: '',
          subject: '',
          body: '',
          senderName: '',
          receiverName: ''
        });
      } else {
        throw new Error(data.message);
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to send email. Please try again.",
        variant: "destructive"
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleAIGeneration = async (prompt: string) => {
    try {
      const response = await fetch('/api/generate-email', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          prompt,
          senderName: formData.senderName,
          receiverName: formData.receiverName,
        }),
      });

      const data = await response.json();
      if (data.status === 'success') {
        setFormData(prev => ({
          ...prev,
          subject: data.subject,
          body: data.body,
        }));
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to generate email content",
        variant: "destructive"
      });
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="mr-2"
          >
            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
            <polyline points="22,6 12,13 2,6" />
          </svg>
          Compose Email
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[525px]">
        <DialogHeader>
          <DialogTitle>Compose Email</DialogTitle>
          <div className="flex items-center space-x-2">
            <Label htmlFor="useAI">Use AI to generate content</Label>
            <Switch
              id="useAI"
              checked={useAI}
              onCheckedChange={setUseAI}
            />
          </div>
        </DialogHeader>
        
        {useAI && (
          <div className="grid w-full gap-1.5">
            <Label htmlFor="prompt">What should the email be about?</Label>
            <Textarea
              id="prompt"
              name="prompt"
              placeholder="Describe what you want the email to say..."
              onChange={(e) => {
                // Generate email content using AI
                handleAIGeneration(e.target.value);
              }}
            />
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid w-full gap-1.5">
            <Label htmlFor="to">To</Label>
            <Input
              id="to"
              name="to"
              type="email"
              placeholder="recipient@example.com"
              value={formData.to}
              onChange={handleInputChange}
              required
            />
          </div>
          <div className="grid w-full gap-1.5">
            <Label htmlFor="subject">Subject</Label>
            <Input
              id="subject"
              name="subject"
              type="text"
              placeholder="Email subject"
              value={formData.subject}
              onChange={handleInputChange}
              required
            />
          </div>
          <div className="grid w-full gap-1.5">
            <Label htmlFor="senderName">Your Name</Label>
            <Input
              id="senderName"
              name="senderName"
              type="text"
              placeholder="Your name"
              value={formData.senderName}
              onChange={handleInputChange}
              required
            />
          </div>
          <div className="grid w-full gap-1.5">
            <Label htmlFor="receiverName">Recipient's Name</Label>
            <Input
              id="receiverName"
              name="receiverName"
              type="text"
              placeholder="Recipient's name"
              value={formData.receiverName}
              onChange={handleInputChange}
              required
            />
          </div>
          <div className="grid w-full gap-1.5">
            <Label htmlFor="body">Message</Label>
            <Textarea
              id="body"
              name="body"
              placeholder="Type your message here"
              value={formData.body}
              onChange={handleInputChange}
              className="h-32"
              required
            />
          </div>
          <div className="flex justify-end space-x-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? "Sending..." : "Send Email"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
