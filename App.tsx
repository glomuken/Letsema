import * as SecureStore from "expo-secure-store";
import { createClient, Session } from "@supabase/supabase-js";
import { StatusBar } from "expo-status-bar";
import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Linking,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL ?? "";
const supabaseKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? "";
const supabase = supabaseUrl && supabaseKey
  ? createClient(supabaseUrl, supabaseKey, {
      auth: {
        storage: {
          getItem: SecureStore.getItemAsync,
          setItem: SecureStore.setItemAsync,
          removeItem: SecureStore.deleteItemAsync,
        },
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: false,
      },
    })
  : null;

type Role = "individual" | "ngo" | "company";
type Profile = {
  id: string; role: Role; name: string; field: string; area: string; resume: string;
  public_token: string; public_enabled: boolean; points: number;
};
type Course = {
  id: string; title: string; field: string; brief: string;
  rubric: { criterion: string; max_points: number }[]; max_points: number;
};
type Project = {
  id: string; ngo_id: string; title: string; field: string; area: string; brief: string;
  budget: number; min_points: number; platform_fee: number; fee_status: string;
  status: string; assigned_to: string | null; delivery_description?: string; delivery_url?: string;
};
type Row = Record<string, any>;
type Page = "Learn" | "Opportunities" | "Repository" | "Projects" | "Talent" | "Profile";

const COLORS = {
  ink: "#173b31", green: "#176b50", lime: "#d9efb0", paper: "#f7f8f2",
  white: "#ffffff", muted: "#63736d", line: "#dce4dc", red: "#a83c32",
};
const PROJECT_COLUMNS = "id,ngo_id,title,field,area,brief,budget,min_points,platform_fee,fee_status,status,assigned_to,created_at";

function money(amount: number) {
  return `R${Number(amount).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function Button({ title, onPress, secondary = false, disabled = false }: {
  title: string; onPress: () => void; secondary?: boolean; disabled?: boolean;
}) {
  return (
    <Pressable disabled={disabled} onPress={onPress}
      style={[styles.button, secondary && styles.secondaryButton, disabled && styles.disabledButton]}>
      <Text style={[styles.buttonText, secondary && styles.secondaryButtonText]}>{title}</Text>
    </Pressable>
  );
}

function Input({ label, value, onChangeText, multiline = false, secureTextEntry = false, keyboardType }: {
  label: string; value: string; onChangeText: (text: string) => void;
  multiline?: boolean; secureTextEntry?: boolean; keyboardType?: "default" | "email-address" | "numeric" | "url";
}) {
  return (
    <View style={styles.inputGroup}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        multiline={multiline}
        secureTextEntry={secureTextEntry}
        keyboardType={keyboardType ?? "default"}
        autoCapitalize={keyboardType === "email-address" ? "none" : "sentences"}
        autoCorrect={keyboardType !== "email-address" && keyboardType !== "url"}
        style={[styles.input, multiline && styles.multiline]}
        placeholderTextColor="#87938d"
      />
    </View>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}

function Heading({ title, detail }: { title: string; detail?: string }) {
  return (
    <View style={styles.heading}>
      <Text style={styles.title}>{title}</Text>
      {detail ? <Text style={styles.detail}>{detail}</Text> : null}
    </View>
  );
}

function AuthScreen({ onSignedIn }: { onSignedIn: () => void }) {
  const [mode, setMode] = useState<"Sign in" | "Create account">("Sign in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!supabase) return;
    if (!email.trim() || !password) return Alert.alert("Missing details", "Enter your email and password.");
    if (mode === "Create account" && password.length < 12) {
      return Alert.alert("Password too short", "Use at least 12 characters.");
    }
    setBusy(true);
    const { data, error } = mode === "Create account"
      ? await supabase.auth.signUp({ email: email.trim(), password })
      : await supabase.auth.signInWithPassword({ email: email.trim(), password });
    setBusy(false);
    if (error) return Alert.alert("Authentication failed", error.message);
    if (data.session) onSignedIn();
    else Alert.alert("Confirm your email", "Check your inbox, then sign in to continue.");
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.authContent} keyboardShouldPersistTaps="handled">
        <Text style={styles.brandMark}>Letsema 🌱</Text>
        <Heading title="Learn by building." detail="Help an NGO. Get discovered." />
        <View style={styles.switchRow}>
          {(["Sign in", "Create account"] as const).map((item) => (
            <Pressable key={item} onPress={() => setMode(item)}
              style={[styles.modeButton, mode === item && styles.modeButtonActive]}>
              <Text style={[styles.modeText, mode === item && styles.modeTextActive]}>{item}</Text>
            </Pressable>
          ))}
        </View>
        <Input label="Email" value={email} onChangeText={setEmail} keyboardType="email-address" />
        <Input label="Password" value={password} onChangeText={setPassword} secureTextEntry />
        <Text style={styles.hint}>{mode === "Create account" ? "Use at least 12 characters." : "Welcome back."}</Text>
        <Button title={busy ? "Please wait…" : "Continue"} onPress={submit} disabled={busy} />
      </ScrollView>
    </SafeAreaView>
  );
}

function Onboarding({ onCreate }: { onCreate: (role: Role, name: string, field: string, area: string) => Promise<void> }) {
  const [role, setRole] = useState<Role>("individual");
  const [name, setName] = useState("");
  const [field, setField] = useState("");
  const [area, setArea] = useState("");
  const labels: Record<Role, string> = { individual: "Individual", ngo: "NGO", company: "Company" };
  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
        <Heading title="Set up your profile" detail="Your role is fixed after onboarding." />
        <Text style={styles.label}>I am an</Text>
        <View style={styles.choiceRow}>
          {(Object.keys(labels) as Role[]).map((item) => (
            <Pressable key={item} onPress={() => setRole(item)}
              style={[styles.choice, role === item && styles.choiceActive]}>
              <Text style={[styles.choiceText, role === item && styles.choiceTextActive]}>{labels[item]}</Text>
            </Pressable>
          ))}
        </View>
        <Input label="Display name" value={name} onChangeText={setName} />
        <Input label="Industry / field" value={field} onChangeText={setField} />
        <Input label="Area / city" value={area} onChangeText={setArea} />
        <Button title="Create profile" onPress={() => void onCreate(role, name, field, area)} />
      </ScrollView>
    </SafeAreaView>
  );
}

function LearnPage({ profile, refreshKey, onRefresh }: { profile: Profile; refreshKey: number; onRefresh: () => void }) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [submissions, setSubmissions] = useState<Row[]>([]);
  const [busyId, setBusyId] = useState("");
  const [forms, setForms] = useState<Record<string, { title: string; evidence: string; url: string }>>({});
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      const [courseResult, submissionResult] = await Promise.all([
        supabase!.from("courses").select("*").order("title"),
        supabase!.from("submissions").select("*").eq("applicant_id", profile.id).not("course_id", "is", null),
      ]);
      if (!active) return;
      if (courseResult.error || submissionResult.error) {
        setError(courseResult.error?.message ?? submissionResult.error?.message ?? "Could not load challenges.");
        return;
      }
      setCourses(courseResult.data as Course[]);
      setSubmissions(submissionResult.data ?? []);
    }
    void load();
    return () => { active = false; };
  }, [profile.id, refreshKey]);

  function update(courseId: string, key: "title" | "evidence" | "url", value: string) {
    setForms((current) => ({
      ...current,
      [courseId]: { ...(current[courseId] ?? { title: "", evidence: "", url: "" }), [key]: value },
    }));
  }

  async function submit(course: Course, prior?: Row) {
    const form = forms[course.id] ?? { title: "", evidence: "", url: "" };
    const input = prior ? { title: prior.title, description: prior.description, artifact_url: prior.artifact_url }
      : { title: form.title.trim(), description: form.evidence.trim(), artifact_url: form.url.trim() };
    if (!input.title || !input.description) return Alert.alert("Add your evidence", "A project title and written evidence are required.");
    setBusyId(course.id);
    setError("");
    const { error: invokeError } = await supabase!.functions.invoke("grade-submission", {
      body: { course_id: course.id, ...input },
    });
    setBusyId("");
    if (invokeError) {
      setError(invokeError.message || "Assessment could not be completed. Your evidence is saved so you can retry.");
      onRefresh();
      return;
    }
    onRefresh();
    Alert.alert("Project assessed", "Your rubric feedback and points are in My repository.");
  }

  return (
    <View>
      <Heading title="Build skills. Earn experience." detail="Complete each project challenge once to earn points." />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {courses.map((course) => {
        const prior = submissions.find((item) => item.course_id === course.id);
        const form = forms[course.id] ?? { title: "", evidence: "", url: "" };
        return (
          <Card key={course.id}>
            <Text style={styles.cardTitle}>{course.title}</Text>
            <Text style={styles.meta}>{course.field} · up to {course.max_points} points</Text>
            <Text style={styles.body}>{course.brief}</Text>
            <Text style={styles.label}>Rubric</Text>
            {course.rubric.map((criterion) => (
              <Text key={criterion.criterion} style={styles.body}>• {criterion.criterion}: {criterion.max_points} points</Text>
            ))}
            {prior?.assessment ? (
              <Text style={styles.success}>Submitted — feedback is available in your repository.</Text>
            ) : (
              <>
                {prior ? <Text style={styles.hint}>Assessment pending. Retry the saved evidence below.</Text> : null}
                <Input label="Project title" value={prior?.title ?? form.title}
                  onChangeText={(value) => update(course.id, "title", value)} />
                <Input label="Written project evidence" value={prior?.description ?? form.evidence}
                  onChangeText={(value) => update(course.id, "evidence", value)} multiline />
                <Input label="Project / repository URL (https://…)" value={prior?.artifact_url ?? form.url}
                  onChangeText={(value) => update(course.id, "url", value)} keyboardType="url" />
                <Text style={styles.hint}>AI assesses written evidence only; it cannot inspect links. Do not submit confidential or personal data.</Text>
                <Button title={busyId === course.id ? "Assessing…" : prior ? "Retry assessment" : "Submit project"}
                  onPress={() => void submit(course, prior)} disabled={busyId === course.id} />
              </>
            )}
          </Card>
        );
      })}
    </View>
  );
}

function OpportunitiesPage({ profile, refreshKey, onAction }: {
  profile: Profile; refreshKey: number; onAction: (name: string, payload: Row) => Promise<void>;
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [pitches, setPitches] = useState<Row[]>([]);
  const [forms, setForms] = useState<Record<string, { message: string; media: string; delivery: string; artifact: string }>>({});
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      const [projectsResult, pitchesResult] = await Promise.all([
        supabase!.from("projects").select(PROJECT_COLUMNS).in("status", ["open", "assigned", "delivered", "complete"]),
        supabase!.from("pitches").select("project_id,applicant_id").eq("applicant_id", profile.id),
      ]);
      if (!active) return;
      if (projectsResult.error || pitchesResult.error) {
        setError(projectsResult.error?.message ?? pitchesResult.error?.message ?? "Could not load opportunities.");
        return;
      }
      setProjects(projectsResult.data as Project[]);
      setPitches(pitchesResult.data ?? []);
    }
    void load();
    return () => { active = false; };
  }, [profile.id, refreshKey]);
  const edit = (id: string, key: "message" | "media" | "delivery" | "artifact", value: string) =>
    setForms((current) => ({
      ...current,
      [id]: { ...(current[id] ?? { message: "", media: "", delivery: "", artifact: "" }), [key]: value },
    }));

  return (
    <View>
      <Heading title="Make a difference" detail="Bring your skills to a real community project." />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {projects.map((project) => {
        const form = forms[project.id] ?? { message: "", media: "", delivery: "", artifact: "" };
        const pitched = pitches.some((pitch) => pitch.project_id === project.id);
        return (
          <Card key={project.id}>
            <Text style={styles.cardTitle}>{project.title}</Text>
            <Text style={styles.meta}>{money(project.budget)} · {project.status}</Text>
            <Text style={styles.body}>{project.brief}</Text>
            <Text style={styles.meta}>{project.field} · {project.area} · minimum {project.min_points} points</Text>
            {project.status === "open" && !pitched && profile.points < project.min_points
              ? <Text style={styles.hint}>Earn {project.min_points - profile.points} more points to pitch.</Text>
              : null}
            {project.status === "open" && !pitched && profile.points >= project.min_points ? (
              <>
                <Input label="Why are you right for this project?" value={form.message}
                  onChangeText={(value) => edit(project.id, "message", value)} multiline />
                <Input label="Video or presentation URL" value={form.media}
                  onChangeText={(value) => edit(project.id, "media", value)} keyboardType="url" />
                <Button title="Send pitch" onPress={() => {
                  if (!form.media.trim()) return Alert.alert("Pitch link required", "Add a video or presentation URL.");
                  void onAction("pitch", { project_id: project.id, message: form.message, media_url: form.media });
                }} />
              </>
            ) : null}
            {project.assigned_to === profile.id && project.status === "assigned" ? (
              <>
                <Input label="Delivery summary" value={form.delivery}
                  onChangeText={(value) => edit(project.id, "delivery", value)} multiline />
                <Input label="Delivered project URL" value={form.artifact}
                  onChangeText={(value) => edit(project.id, "artifact", value)} keyboardType="url" />
                <Button title="Submit completed work" onPress={() => {
                  void onAction("deliver_project", { project_id: project.id, description: form.delivery, artifact_url: form.artifact });
                }} />
              </>
            ) : null}
          </Card>
        );
      })}
      {projects.length === 0 && !error ? <Text style={styles.hint}>No opportunities are open right now.</Text> : null}
    </View>
  );
}

function RepositoryPage({ profile, refreshKey }: { profile: Profile; refreshKey: number }) {
  const [submissions, setSubmissions] = useState<Row[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [reviews, setReviews] = useState<Row[]>([]);
  useEffect(() => {
    let active = true;
    async function load() {
      const [s, p, r] = await Promise.all([
        supabase!.from("submissions").select("*").eq("applicant_id", profile.id).order("created_at", { ascending: false }),
        supabase!.from("projects").select(PROJECT_COLUMNS).eq("assigned_to", profile.id),
        supabase!.from("reviews").select("*").eq("applicant_id", profile.id),
      ]);
      if (!active) return;
      const issue = s.error ?? p.error ?? r.error;
      if (issue) return Alert.alert("Could not load repository", issue.message);
      setSubmissions(s.data ?? []); setProjects(p.data as Project[]); setReviews(r.data ?? []);
    }
    void load();
    return () => { active = false; };
  }, [profile.id, refreshKey]);

  return (
    <View>
      <Heading title="Your work and feedback" detail="A record of learning and real-world projects." />
      {submissions.map((item) => {
        const learning = Boolean(item.course_id);
        return (
          <Card key={item.id}>
            <Text style={styles.cardTitle}>{learning ? "Learning" : "NGO"} · {item.title}</Text>
            <Text style={styles.body}>{item.description}</Text>
            {item.artifact_url ? <Text style={styles.linkText} onPress={() => void Linking.openURL(item.artifact_url)}>Open project ↗</Text> : null}
            {learning ? <Text style={styles.success}>{item.points ?? 0} points</Text> : null}
            <Text style={styles.body}>{item.assessment?.feedback ?? (learning ? "Assessment pending." : "")}</Text>
            {item.assessment?.scores?.map((score: Row) => (
              <Text key={score.criterion} style={styles.meta}>{score.criterion}: {score.score} · {score.feedback}</Text>
            ))}
          </Card>
        );
      })}
      {projects.map((item) => (
        <Card key={item.id}>
          <Text style={styles.cardTitle}>NGO project · {item.title}</Text>
          <Text style={styles.meta}>Status: {item.status}</Text>
          {item.delivery_url ? <Text style={styles.linkText} onPress={() => void Linking.openURL(item.delivery_url!)}>Delivered artifact ↗</Text> : null}
        </Card>
      ))}
      {reviews.map((item) => <Card key={item.id}><Text style={styles.cardTitle}>NGO review · {item.rating}/5</Text><Text style={styles.body}>{item.body}</Text></Card>)}
      {!submissions.length && !projects.length && !reviews.length
        ? <Text style={styles.hint}>Complete a learning challenge to start your project repository.</Text> : null}
    </View>
  );
}

function ProfilePage({ profile, refreshKey, onAction }: {
  profile: Profile; refreshKey: number; onAction: (name: string, payload: Row) => Promise<void>;
}) {
  const [name, setName] = useState(profile.name);
  const [field, setField] = useState(profile.field);
  const [area, setArea] = useState(profile.area);
  const [resume, setResume] = useState(profile.resume ?? "");
  const [share, setShare] = useState(profile.public_enabled);
  useEffect(() => {
    setName(profile.name); setField(profile.field); setArea(profile.area);
    setResume(profile.resume ?? ""); setShare(profile.public_enabled);
  }, [profile, refreshKey]);
  return (
    <View>
      <Heading title="Your profile" detail="Keep your skills and experience up to date." />
      <Card>
        <Input label="Display name" value={name} onChangeText={setName} />
        <Input label="Industry / field" value={field} onChangeText={setField} />
        <Input label="Area / city" value={area} onChangeText={setArea} />
        <Input label="Resume, skills and experience" value={resume} onChangeText={setResume} multiline />
        {profile.role === "individual" ? (
          <View style={styles.toggleRow}>
            <Text style={styles.body}>Share portfolio and appear in talent lists</Text>
            <Switch value={share} onValueChange={setShare} trackColor={{ true: COLORS.green }} />
          </View>
        ) : null}
        <Button title="Save profile" onPress={() => void onAction("update_profile", {
          name, field, area, resume, public_enabled: profile.role === "individual" && share,
        })} />
      </Card>
      {profile.role === "individual" && share ? (
        <Card>
          <Text style={styles.cardTitle}>Public portfolio</Text>
          <Text style={styles.body}>Anyone with this link can see your resume, projects and reviews. Turning sharing off revokes access.</Text>
          <Button title="Share portfolio link" secondary onPress={() => void Share.share({
          message: `View ${profile.name}'s Letsema portfolio: letsema://portfolio?token=${encodeURIComponent(profile.public_token)}`,
          })} />
        </Card>
      ) : null}
    </View>
  );
}

function NgoProjectsPage({ profile, refreshKey, onAction }: {
  profile: Profile; refreshKey: number; onAction: (name: string, payload: Row) => Promise<void>;
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [pitches, setPitches] = useState<Record<string, Row[]>>({});
  const [title, setTitle] = useState("");
  const [field, setField] = useState(profile.field);
  const [area, setArea] = useState(profile.area);
  const [brief, setBrief] = useState("");
  const [budget, setBudget] = useState("500");
  const [minimum, setMinimum] = useState("0");
  const [payment, setPayment] = useState<Record<string, string>>({});
  const [review, setReview] = useState<Record<string, { reference: string; body: string; rating: string }>>({});
  const [openCreate, setOpenCreate] = useState(false);
  useEffect(() => {
    let active = true;
    async function load() {
      const result = await supabase!.from("projects").select(PROJECT_COLUMNS).eq("ngo_id", profile.id).order("created_at", { ascending: false });
      if (!active) return;
      if (result.error) return Alert.alert("Could not load projects", result.error.message);
      const ownProjects = result.data as Project[];
      setProjects(ownProjects);
      const pitchResults = await Promise.all(ownProjects.filter((p) => p.status === "open").map(async (p) => {
        const response = await supabase!.from("pitches").select("*").eq("project_id", p.id);
        if (response.error) throw response.error;
        return [p.id, response.data ?? []] as const;
      }));
      if (active) setPitches(Object.fromEntries(pitchResults));
    }
    void load().catch((error: Error) => Alert.alert("Could not load pitches", error.message));
    return () => { active = false; };
  }, [profile.id, refreshKey]);

  return (
    <View>
      <Heading title="Affordable help. Real impact." detail="Amounts are ZAR. The 10% platform fee is declared and paid separately." />
      <Card>
        <Text style={styles.body}>This app records manual payment references; it does not charge cards, hold escrow, or verify transfers.</Text>
        <Button title={openCreate ? "Close project form" : "Post a project"} secondary onPress={() => setOpenCreate(!openCreate)} />
        {openCreate ? (
          <>
            <Input label="Project title" value={title} onChangeText={setTitle} />
            <Input label="Industry / field" value={field} onChangeText={setField} />
            <Input label="Area / city" value={area} onChangeText={setArea} />
            <Input label="Project brief and acceptance criteria" value={brief} onChangeText={setBrief} multiline />
            <Input label="Applicant payment (ZAR)" value={budget} onChangeText={setBudget} keyboardType="numeric" />
            <Input label="Minimum points to pitch" value={minimum} onChangeText={setMinimum} keyboardType="numeric" />
            <Button title="Create draft project" onPress={() => {
              const amount = Number(budget), points = Number(minimum);
              if (!Number.isFinite(amount) || amount <= 0 || !Number.isInteger(points) || points < 0) {
                return Alert.alert("Check project values", "Enter a positive budget and a whole number of points.");
              }
              void onAction("create_project", { title, field, area, brief, budget: amount, min_points: points });
            }} />
          </>
        ) : null}
      </Card>
      {projects.map((project) => (
        <NgoProjectCard key={project.id} project={project} pitches={pitches[project.id] ?? []}
          payment={payment[project.id] ?? ""} setPayment={(value) => setPayment((prev) => ({ ...prev, [project.id]: value }))}
          review={review[project.id] ?? { reference: "", body: "", rating: "5" }}
          setReview={(value) => setReview((prev) => ({ ...prev, [project.id]: value }))}
          onAction={onAction} />
      ))}
    </View>
  );
}

function NgoProjectCard({ project, pitches, payment, setPayment, review, setReview, onAction }: {
  project: Project; pitches: Row[]; payment: string; setPayment: (value: string) => void;
  review: { reference: string; body: string; rating: string };
  setReview: (value: { reference: string; body: string; rating: string }) => void;
  onAction: (name: string, payload: Row) => Promise<void>;
}) {
  const [feeRef, setFeeRef] = useState("");
  return (
    <Card>
      <Text style={styles.cardTitle}>{project.title} · {project.status}</Text>
      <Text style={styles.body}>{project.brief}</Text>
      <Text style={styles.meta}>Applicant budget: {money(project.budget)} · Platform fee: {money(project.platform_fee)}</Text>
      {project.status === "draft" ? (
        <>
          <Input label="Manual platform fee payment reference" value={feeRef} onChangeText={setFeeRef} />
          <Button title="Record fee and publish" onPress={() => {
            if (!feeRef.trim()) return Alert.alert("Reference required", "Add the manual fee payment reference.");
            Alert.alert("Confirm payment", "Confirm that you paid the platform fee outside this app.", [
              { text: "Cancel", style: "cancel" },
              { text: "I have paid", onPress: () => void onAction("record_platform_fee", { project_id: project.id, reference: feeRef }) },
            ]);
          }} />
        </>
      ) : null}
      {project.status === "open" ? pitches.map((pitch) => (
        <View key={pitch.id} style={styles.pitch}>
          <Text style={styles.body}>{pitch.message}</Text>
          <Text style={styles.meta}>Applicant: {pitch.applicant_id}</Text>
          <Text style={styles.linkText} onPress={() => void Linking.openURL(pitch.media_url)}>View presentation ↗</Text>
          <Button title="Assign this applicant" secondary onPress={() => void onAction("assign_project", {
            project_id: project.id, applicant_id: pitch.applicant_id,
          })} />
        </View>
      )) : null}
      {project.status === "delivered" ? (
        <>
          <Text style={styles.body}>{project.delivery_description}</Text>
          {project.delivery_url ? <Text style={styles.linkText} onPress={() => void Linking.openURL(project.delivery_url!)}>Review delivered work ↗</Text> : null}
          <Input label="Manual applicant payment reference" value={review.reference}
            onChangeText={(value) => setReview({ ...review, reference: value })} />
          <Input label="Rating (1–5)" value={review.rating} onChangeText={(value) => setReview({ ...review, rating: value })} keyboardType="numeric" />
          <Input label="Your review" value={review.body} onChangeText={(value) => setReview({ ...review, body: value })} multiline />
          <Button title="Complete project and review" onPress={() => {
            if (!/^[1-5]$/.test(review.rating)) return Alert.alert("Invalid rating", "Choose a whole number from 1 to 5.");
            Alert.alert("Confirm completion", "Confirm that you accepted the work and paid the applicant outside this app.", [
              { text: "Cancel", style: "cancel" },
              { text: "Confirm", onPress: () => void onAction("complete_project", {
                project_id: project.id, payment_reference: review.reference,
                rating: Number(review.rating), body: review.body,
              }) },
            ]);
          }} />
        </>
      ) : null}
    </Card>
  );
}

function TalentPage({ profile, refreshKey, onAction, onViewPortfolio }: {
  profile: Profile; refreshKey: number; onAction: (name: string, payload: Row) => Promise<void>;
  onViewPortfolio: (token: string) => void;
}) {
  const [field, setField] = useState(profile.field);
  const [area, setArea] = useState(profile.area);
  const [digests, setDigests] = useState<Row[]>([]);
  useEffect(() => {
    let active = true;
    async function load() {
      const { data, error } = await supabase!.rpc("weekly_digest");
      if (!active) return;
      if (error) return Alert.alert("Could not load talent lists", error.message);
      setDigests(data ?? []);
    }
    void load();
    return () => { active = false; };
  }, [profile.id, refreshKey]);
  return (
    <View>
      <Heading title="Find your next junior hire" detail="Weekly in-app lists include applicants who opted into public sharing." />
      <Card>
        <Input label="Industry / field" value={field} onChangeText={setField} />
        <Input label="Area / city" value={area} onChangeText={setArea} />
        <Button title="Subscribe to weekly list" onPress={() => void onAction("subscribe", { field, area })} />
      </Card>
      {digests.map((digest) => (
        <Card key={digest.id}>
          <Text style={styles.cardTitle}>{digest.field} · {digest.area}</Text>
          <Text style={styles.meta}>Week: {digest.week ?? digest.week_start}</Text>
          {(digest.talent ?? []).map((candidate: Row, index: number) => (
            <View key={candidate.id} style={styles.candidate}>
              <Text style={styles.body}>{index + 1}. {candidate.name} · {candidate.points} points</Text>
              <Button title="Open public portfolio" secondary onPress={() => onViewPortfolio(candidate.public_token)} />
            </View>
          ))}
          {!(digest.talent ?? []).length ? <Text style={styles.hint}>No matching public applicants this week.</Text> : null}
          <Button title="Unsubscribe" secondary onPress={() => void onAction("unsubscribe", { subscription_id: digest.id })} />
        </Card>
      ))}
    </View>
  );
}

function PublicPortfolio({ token, onExit }: { token: string; onExit: () => void }) {
  const [data, setData] = useState<Row | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    void supabase!.rpc("public_portfolio", { token }).then(({ data: result, error }) => {
      if (!active) return;
      setData(error ? null : result); setLoading(false);
    });
    return () => { active = false; };
  }, [token]);
  if (loading) return <View style={styles.center}><ActivityIndicator color={COLORS.green} /></View>;
  return (
    <ScrollView contentContainerStyle={styles.page}>
      {data ? (
        <>
          <Heading title={data.profile.name} detail={`${data.profile.field} · ${data.profile.area}`} />
          <Card><Text style={styles.success}>{data.profile.points} experience points</Text><Text style={styles.body}>{data.profile.resume || "No resume added yet."}</Text></Card>
          <Heading title="Project repository" />
          {[...(data.submissions ?? []), ...(data.projects ?? [])].map((item: Row) => (
            <Card key={item.id}>
              <Text style={styles.cardTitle}>{item.title}</Text>
              <Text style={styles.body}>{item.description ?? item.delivery_description ?? item.brief}</Text>
              {(item.artifact_url || item.delivery_url) ? (
                <Text style={styles.linkText} onPress={() => void Linking.openURL(item.artifact_url || item.delivery_url)}>View project ↗</Text>
              ) : null}
            </Card>
          ))}
          {(data.reviews ?? []).map((item: Row) => <Card key={item.id}><Text style={styles.cardTitle}>NGO review · {item.rating}/5</Text><Text style={styles.body}>{item.body}</Text></Card>)}
        </>
      ) : <Text style={styles.hint}>This portfolio is unavailable or sharing has been disabled.</Text>}
      <Button title="Go to Letsema" onPress={onExit} />
    </ScrollView>
  );
}

function AppContent() {
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(Boolean(supabase));
  const [profileLoading, setProfileLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [page, setPage] = useState<Page>("Learn");
  const [portfolioToken, setPortfolioToken] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const readToken = (url: string | null) => {
      if (!url) return;
      const query = url.split("?")[1]?.split("#")[0] ?? "";
      const match = query.match(/(?:^|&)(?:token|profile)=([^&]*)/);
      if (match) {
        try {
          setPortfolioToken(decodeURIComponent(match[1].replace(/\+/g, " ")));
        } catch {
          setPortfolioToken("");
        }
      }
    };
    void Linking.getInitialURL().then(readToken);
    const listener = Linking.addEventListener("url", ({ url }) => readToken(url));
    return () => listener.remove();
  }, []);

  useEffect(() => {
    if (!supabase) { setLoading(false); return; }
    void supabase.auth.getSession().then(({ data }) => { setSession(data.session); setLoading(false); });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setProfileLoading(Boolean(nextSession));
      if (!nextSession) { setProfile(null); setPage("Learn"); }
    });
    return () => listener.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!supabase || !session?.user.id) {
      setProfile(null);
      setProfileLoading(false);
      return;
    }
    let active = true;
    setProfileLoading(true);
    setError("");
    void supabase.from("profiles").select("*").eq("id", session.user.id).maybeSingle().then(({ data, error: queryError }) => {
      if (!active) return;
      setProfileLoading(false);
      if (queryError) { setError(queryError.message); return; }
      const nextProfile = data as Profile | null;
      setProfile(nextProfile);
      if (nextProfile) {
        setPage((current) => current === "Learn"
          ? nextProfile.role === "ngo" ? "Projects" : nextProfile.role === "company" ? "Talent" : "Learn"
          : current);
      }
    });
    return () => { active = false; };
  }, [session?.user.id, refreshKey]);

  const refresh = useCallback(() => setRefreshKey((value) => value + 1), []);
  async function action(name: string, payload: Row) {
    if (!supabase) return;
    setError("");
    const { error: actionError } = await supabase.rpc("letsema_action", { action_name: name, payload });
    if (actionError) {
      setError(actionError.message);
      Alert.alert("Could not save", actionError.message);
      return;
    }
    refresh();
  }
  async function createProfile(role: Role, name: string, field: string, area: string) {
    await action("create_profile", { role, name, field, area });
  }
  async function signOut() {
    const { error: signOutError } = await supabase!.auth.signOut();
    if (signOutError) Alert.alert("Could not sign out", signOutError.message);
  }

  if (portfolioToken && supabase) {
    return <PublicPortfolio token={portfolioToken} onExit={() => setPortfolioToken("")} />;
  }
  if (!supabase) {
    return (
      <View style={styles.center}>
        <Text style={styles.brand}>Letsema 🌱</Text>
        <Text style={styles.title}>Connect your Supabase project</Text>
        <Text style={styles.detail}>Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY, then restart Expo.</Text>
      </View>
    );
  }
  if (loading) return <View style={styles.center}><ActivityIndicator size="large" color={COLORS.green} /></View>;
  if (!session) return <AuthScreen onSignedIn={() => refresh()} />;
  if (profileLoading && !profile) return <View style={styles.center}><ActivityIndicator size="large" color={COLORS.green} /></View>;
  if (!profile && error) {
    return (
      <SafeAreaView style={styles.center}>
        <Text style={styles.title}>Could not load your profile</Text>
        <Text style={styles.detail}>{error}</Text>
        <Button title="Retry" onPress={() => { setError(""); refresh(); }} />
      </SafeAreaView>
    );
  }
  if (!profile) return <Onboarding onCreate={createProfile} />;

  const pages: Page[] = profile.role === "individual"
    ? ["Learn", "Opportunities", "Repository", "Profile"]
    : profile.role === "ngo" ? ["Projects", "Profile"] : ["Talent", "Profile"];
  const visiblePage = pages.includes(page) ? page : pages[0];
  let pageContent: React.ReactNode;
  switch (visiblePage) {
    case "Learn": pageContent = <LearnPage profile={profile} refreshKey={refreshKey} onRefresh={refresh} />; break;
    case "Opportunities": pageContent = <OpportunitiesPage profile={profile} refreshKey={refreshKey} onAction={action} />; break;
    case "Repository": pageContent = <RepositoryPage profile={profile} refreshKey={refreshKey} />; break;
    case "Projects": pageContent = <NgoProjectsPage profile={profile} refreshKey={refreshKey} onAction={action} />; break;
    case "Talent": pageContent = <TalentPage profile={profile} refreshKey={refreshKey} onAction={action} onViewPortfolio={setPortfolioToken} />; break;
    default: pageContent = <ProfilePage profile={profile} refreshKey={refreshKey} onAction={action} />;
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="dark" />
      <View style={styles.appHeader}>
        <View>
          <Text style={styles.brand}>Letsema 🌱</Text>
          <Text style={styles.welcome}>Welcome, {profile.name}</Text>
        </View>
        <Pressable onPress={() => void signOut()}><Text style={styles.signOut}>Sign out</Text></Pressable>
      </View>
      {profile.role === "individual" ? (
        <View style={styles.pointsCard}>
          <Text style={styles.points}>{profile.points} points</Text>
          <Text style={styles.pointsHint}>Level {Math.floor(profile.points / 100) + 1} · {100 - profile.points % 100} to next level</Text>
        </View>
      ) : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView style={styles.main} contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
        {pageContent}
      </ScrollView>
      <View style={styles.tabBar}>
        {pages.map((item) => (
          <Pressable key={item} onPress={() => setPage(item)} style={styles.tab}>
            <Text style={[styles.tabText, visiblePage === item && styles.tabTextActive]}>{item}</Text>
          </Pressable>
        ))}
      </View>
    </SafeAreaView>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <AppContent />
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: COLORS.paper },
  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 28, backgroundColor: COLORS.paper, gap: 12 },
  authContent: { flexGrow: 1, justifyContent: "center", padding: 24, backgroundColor: COLORS.paper },
  page: { padding: 20, paddingBottom: 36, gap: 14 },
  appHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 20, paddingVertical: 14 },
  brand: { color: COLORS.ink, fontWeight: "900", fontSize: 21 },
  brandMark: { color: COLORS.green, fontWeight: "900", fontSize: 30, marginBottom: 24 },
  welcome: { color: COLORS.muted, fontSize: 13, marginTop: 2 },
  signOut: { color: COLORS.green, fontWeight: "700", padding: 8 },
  pointsCard: { marginHorizontal: 20, padding: 16, borderRadius: 16, backgroundColor: COLORS.ink, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  points: { color: COLORS.lime, fontWeight: "800", fontSize: 18 },
  pointsHint: { color: "#d8e2dc", fontSize: 12 },
  main: { flex: 1 },
  heading: { gap: 5, marginBottom: 4 },
  title: { color: COLORS.ink, fontSize: 25, fontWeight: "800" },
  detail: { color: COLORS.muted, fontSize: 15, lineHeight: 22 },
  card: { backgroundColor: COLORS.white, borderWidth: 1, borderColor: COLORS.line, borderRadius: 18, padding: 17, gap: 10 },
  cardTitle: { color: COLORS.ink, fontWeight: "800", fontSize: 17 },
  body: { color: COLORS.ink, fontSize: 15, lineHeight: 22 },
  meta: { color: COLORS.muted, fontSize: 13, lineHeight: 19 },
  hint: { color: COLORS.muted, fontSize: 13, lineHeight: 19, marginVertical: 2 },
  success: { color: COLORS.green, fontWeight: "700", fontSize: 14 },
  error: { color: COLORS.red, paddingHorizontal: 20, paddingVertical: 8, lineHeight: 20 },
  label: { color: COLORS.ink, fontSize: 13, fontWeight: "700" },
  inputGroup: { gap: 6, marginVertical: 3 },
  input: { minHeight: 48, borderColor: COLORS.line, borderWidth: 1, borderRadius: 12, paddingHorizontal: 13, paddingVertical: 11, fontSize: 15, color: COLORS.ink, backgroundColor: "#fcfdfb" },
  multiline: { minHeight: 110, textAlignVertical: "top" },
  button: { minHeight: 48, backgroundColor: COLORS.green, borderRadius: 13, justifyContent: "center", alignItems: "center", paddingHorizontal: 16, marginTop: 4 },
  buttonText: { color: COLORS.white, fontSize: 15, fontWeight: "800" },
  secondaryButton: { backgroundColor: COLORS.lime },
  secondaryButtonText: { color: COLORS.ink },
  disabledButton: { opacity: 0.55 },
  switchRow: { flexDirection: "row", backgroundColor: "#e8eee8", borderRadius: 13, padding: 4, marginBottom: 15 },
  modeButton: { flex: 1, alignItems: "center", padding: 11, borderRadius: 10 },
  modeButtonActive: { backgroundColor: COLORS.white },
  modeText: { color: COLORS.muted, fontWeight: "700" },
  modeTextActive: { color: COLORS.ink },
  choiceRow: { flexDirection: "row", gap: 7, marginBottom: 12 },
  choice: { flex: 1, borderRadius: 12, borderWidth: 1, borderColor: COLORS.line, paddingVertical: 12, alignItems: "center" },
  choiceActive: { backgroundColor: COLORS.ink, borderColor: COLORS.ink },
  choiceText: { color: COLORS.ink, fontSize: 12, fontWeight: "700" },
  choiceTextActive: { color: COLORS.white },
  linkText: { color: COLORS.green, fontWeight: "700", paddingVertical: 5 },
  tabBar: { flexDirection: "row", borderTopWidth: 1, borderTopColor: COLORS.line, backgroundColor: COLORS.white, paddingVertical: 9, paddingHorizontal: 4 },
  tab: { flex: 1, alignItems: "center", justifyContent: "center", paddingVertical: 8 },
  tabText: { color: COLORS.muted, fontSize: 11, fontWeight: "700", textAlign: "center" },
  tabTextActive: { color: COLORS.green },
  toggleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  pitch: { borderTopWidth: 1, borderColor: COLORS.line, paddingTop: 12, gap: 8 },
  candidate: { borderTopWidth: 1, borderColor: COLORS.line, paddingTop: 10, gap: 5 },
});
