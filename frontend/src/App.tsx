import { useState, useEffect } from 'react';

interface Task {
  id: string;
  text: string;
  completed: boolean;
}

interface Achievement {
  id: string;
  title: string;
  description: string;
  category: string;
  date_earned: string;
}

type Tab = 'tasks' | 'timer' | 'achievements' | 'chat';

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('tasks');
  const [selectedUser, setSelectedUser] = useState<string>('riya');

  // PANEL 1: Checklist State
  const [tasks, setTasks] = useState<Task[]>([]);
  const [newTaskText, setNewTaskText] = useState('');

  // PANEL 2: Focus Timer State
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [isRunning, setIsRunning] = useState(false);

  // PANEL 3: Trophy Wall State
  const [achievements, setAchievements] = useState<Achievement[]>([]);
  const [hasAchievements, setHasAchievements] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Focus Timer Tick effect
  useEffect(() => {
    let interval: number | undefined;
    if (isRunning) {
      interval = window.setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else {
      if (interval) clearInterval(interval);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isRunning]);

  // Fetch Achievements when selectedUser changes (and on mount)
  useEffect(() => {
    fetchAchievements(selectedUser);
  }, [selectedUser]);

  // API Calls
  const logChecklistToBackend = async (currentTasks: Task[]) => {
    const completedCount = currentTasks.filter((t) => t.completed).length;
    const totalCount = currentTasks.length;
    try {
      const res = await fetch('http://127.0.0.1:8000/checklist', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: selectedUser,
          completed_count: completedCount,
          total_count: totalCount,
        }),
      });
      if (res.ok) {
        fetchAchievements(selectedUser);
      }
    } catch (err) {
      console.error('Failed to log checklist progress:', err);
    }
  };

  const handleAddTask = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTaskText.trim()) return;
    const updated = [
      ...tasks,
      { id: Date.now().toString(), text: newTaskText.trim(), completed: false },
    ];
    setTasks(updated);
    setNewTaskText('');
    logChecklistToBackend(updated);
  };

  const handleToggleTask = (id: string) => {
    const updated = tasks.map((task) =>
      task.id === id ? { ...task, completed: !task.completed } : task
    );
    setTasks(updated);
    logChecklistToBackend(updated);
  };

  const handleLogFocus = async () => {
    setIsRunning(false);
    const durationMinutes = elapsedSeconds / 60;
    try {
      const res = await fetch('http://127.0.0.1:8000/timer', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: selectedUser,
          duration_minutes: durationMinutes,
        }),
      });
      if (res.ok) {
        fetchAchievements(selectedUser);
      }
    } catch (err) {
      console.error('Failed to log focus timer:', err);
    }
    setElapsedSeconds(0);
  };

  const fetchAchievements = async (userId: string = selectedUser) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`http://127.0.0.1:8000/achievements/${userId}`);
      if (!res.ok) {
        throw new Error('Failed to fetch');
      }
      const data = await res.json();
      setHasAchievements(data.has_achievements);
      setAchievements(data.achievements || []);
    } catch (err) {
      console.error('Error fetching achievements:', err);
      setError('Could not load achievements. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  // Helper for formatting time MM:SS
  const formatTime = (totalSecs: number) => {
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const getTabStyle = (tab: Tab) => ({
    flex: 1,
    height: '100%',
    border: 'none',
    backgroundColor: 'transparent',
    color: activeTab === tab ? 'var(--color-primary)' : 'var(--color-text)',
    borderBottom: activeTab === tab ? '3px solid var(--color-primary)' : 'none',
    cursor: 'pointer',
    fontSize: '1rem',
    fontWeight: activeTab === tab ? ('bold' as const) : ('normal' as const),
  });

  const panelStyle = {
    width: '100%',
    borderRight: 'none',
    height: 'calc(100vh - 60px)',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', width: '100%' }}>
      {/* Tab Bar */}
      <nav style={{ display: 'flex', alignItems: 'center', width: '100%', height: '60px', borderBottom: '1px solid var(--color-accent)', backgroundColor: 'var(--color-bg)', paddingRight: '1rem' }}>
        <div style={{ display: 'flex', flexGrow: 1, height: '100%' }}>
          <button style={getTabStyle('tasks')} onClick={() => setActiveTab('tasks')}>Tasks</button>
          <button style={getTabStyle('timer')} onClick={() => setActiveTab('timer')}>Timer</button>
          <button style={getTabStyle('achievements')} onClick={() => setActiveTab('achievements')}>Achievements</button>
          <button style={getTabStyle('chat')} onClick={() => setActiveTab('chat')}>Chat</button>
        </div>
        <select
          value={selectedUser}
          onChange={(e) => setSelectedUser(e.target.value)}
          style={{
            padding: '0.25rem 0.5rem',
            border: '1px solid var(--color-primary)',
            backgroundColor: 'var(--color-bg)',
            color: 'var(--color-text)',
            fontSize: '0.9rem',
            outline: 'none'
          }}
        >
          <option value="riya">riya</option>
          <option value="sam">sam</option>
          <option value="diego">diego</option>
          <option value="bex">bex</option>
          <option value="casey">casey</option>
        </select>
      </nav>

      {/* Content */}
      <div style={{ display: 'flex', flexGrow: 1 }}>
        {activeTab === 'tasks' && (
          <section className="panel" style={panelStyle}>
            <h2 className="panel-title">Today's Tasks</h2>
            <form onSubmit={handleAddTask} className="input-group">
              <input
                type="text"
                className="text-input"
                placeholder="Add a task..."
                value={newTaskText}
                onChange={(e) => setNewTaskText(e.target.value)}
              />
              <button type="submit" className="btn">Add</button>
            </form>

            <ul className="task-list">
              {tasks.map((task) => (
                <li key={task.id} className="task-item">
                  <input
                    type="checkbox"
                    className="task-checkbox"
                    checked={task.completed}
                    onChange={() => handleToggleTask(task.id)}
                    id={`task-check-${task.id}`}
                  />
                  <span
                    className={`task-text ${task.completed ? 'completed' : ''}`}
                    onClick={() => handleToggleTask(task.id)}
                  >
                    {task.text}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {activeTab === 'timer' && (
          <section className="panel" style={panelStyle}>
            <h2 className="panel-title">Focus Timer</h2>
            <div className="timer-container">
              <div className="timer-display">{formatTime(elapsedSeconds)}</div>
              <div className="btn-group">
                {!isRunning ? (
                  <button onClick={() => setIsRunning(true)} className="btn">
                    Start
                  </button>
                ) : (
                  <button onClick={() => setIsRunning(false)} className="btn btn-secondary">
                    Pause
                  </button>
                )}
                <button onClick={handleLogFocus} className="btn btn-accent" disabled={elapsedSeconds === 0}>
                  Log Focus
                </button>
              </div>
            </div>
          </section>
        )}

        {activeTab === 'achievements' && (
          <section className="panel" style={panelStyle}>
            <h2 className="panel-title">Your Achievements</h2>
            <div className="trophy-wall">
              <div className="refresh-container">
                <button onClick={() => fetchAchievements()} className="btn btn-secondary" disabled={loading}>
                  Refresh
                </button>
              </div>

              {loading && <div className="status-text">Loading your achievements...</div>}

              {!loading && error && (
                <div className="status-text error-text">{error}</div>
              )}

              {!loading && !error && hasAchievements === false && (
                <div className="empty-wall">
                  <h3 className="empty-wall-heading">Your wall is waiting.</h3>
                  <p className="empty-wall-subtext">
                    Nothing here yet — and that's alright. Trophies show up
                    when the data says you earned them, not before. Show up this week,
                    and let's see what you've got.
                  </p>
                </div>
              )}

              {!loading && !error && hasAchievements === true && (
                <div className="cards-grid">
                  {achievements.map((achievement) => (
                    <div key={achievement.id} className="achievement-card">
                      <div className="achievement-header">
                        <span className="achievement-title">{achievement.title}</span>
                        <span className="badge">{achievement.category}</span>
                      </div>
                      <p className="achievement-desc">{achievement.description}</p>
                      <div className="achievement-date">
                        Earned: {new Date(achievement.date_earned).toLocaleDateString()}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        )}

        {activeTab === 'chat' && (
          <iframe
            src="http://127.0.0.1:18081"
            style={{ width: '100%', height: 'calc(100vh - 60px)', border: 'none' }}
          />
        )}
      </div>
    </div>
  );
}
