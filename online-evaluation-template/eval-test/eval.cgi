#!/usr/bin/perl -w
use strict;
use warnings;
use LWP;
use CGI;
use HTML::Template;

my $logfile  = 'submit.log';
my $errfile  = 'error.log';
my $timefile = 'time.log';
my $access_limit = 24;
my $listfile = 'files.lst';
my $sfile    = 'submission.tar.gz';
my $gdir     = 'gold';
my $wdir     = 'work';
my $cdir     = 'collect';


# to specify the scripts for format checking and evaluation.
my $checker     = "../tools/a2-normalize.pl -u -g $gdir";
my $evaluator   = "../tools/a2-evaluate.pl -g $gdir";


# these two are specific to the GE task
my $decomposer  = "../tools/a2-decompose.pl";
my $devaluator  = "../tools/a2d-evaluate.pl -g $gdir";


my %userlist;
my $ua = LWP::UserAgent->new;
$ua->credentials('ml.bionlp-st.org:80', 'Restricted Area', 'sharedtask' => '2013acl');
my $res = $ua->get('http://ml.bionlp-st.org/list');
my @email = split(/\n/, $res->content);
if (!@email) {&PrintMessage("Cannot get the list of registered e-mails")}
foreach (@email) {
    chomp;
    $userlist{$_} = 1;
}

my $query    = new CGI;
my $email    = $query->param('email');
my $fname    = $query->param('file');
my $analysis = $query->param('analysis');

## check input fields
if (!$userlist{$email})    {&PrintMessage("Your E-mail address is not registered.")}
if ($fname !~ /\.tar.gz$/) {&PrintMessage("We only accept submission of a *.tar.gz file containing all *.a2 files.")}

&logging($email, "access."); 

if ($analysis eq 'on') {$evaluator .= ' -x'; $devaluator .= ' -x'}

## prepare working directory
$wdir .= '/' . $email;

umask 0000;
mkdir($wdir, 0777) || &PrintMessage("Your previous submission is still being processed. Please wait and retry.");

## prepare files to be tested
my ($buf, $file) = ('', '');
my $fh = $query->upload('file');
while (read($fh, $buf, 1024)) {$file .= $buf}

if (!open (FILE, '>' . $wdir . '/'. $sfile)) {
    system ("rm -r $wdir");
    &logging($email, "failed to open the working file.");
    &PrintMessage("Failed to open the working file. Please try again.")
} # if
print FILE $file;
close (FILE);

## unpack files
my $cmd = "tar -xzf $wdir/$sfile -C $wdir";
my $errmsg = `$cmd 2>&1`;
if ($errmsg) {
    sleep 2;
    $errmsg = `$cmd 2>&1`;
} # if

if ($errmsg) {
    system ("rm -r $wdir");
    &logging ($email, "failed to unpack:\n$errmsg\n" . `which tar`);
    &PrintMessage("Failed to unpack. Please check your tar.gz file and try again.");
} # if


## check missing or extra files
open (FILE, '<' . $listfile) ;
my @pmid = <FILE>; chomp (@pmid);
close (FILE);
my %pmid = map { $_ => 1 } @pmid;

my @extrafile = ();

opendir(WDIR, $wdir);
while (my $fname = readdir(WDIR)) {
    next if ($fname eq '.' || $fname eq '..' || $fname eq 'submission.tar.gz');
    if ($pmid{$fname}) {delete $pmid{$fname}}
    else {
        push @extrafile, $fname;
        system("rm $wdir/$fname");
    }
}
closedir(WDIR);

my @missingfile = sort keys %pmid;

if (@missingfile || @extrafile) {
    system ("rm -r $wdir");
    &logging ($email, $#missingfile+1 . " missing files.");
    &logging ($email, $#extrafile+1 . " extra files.");

    $errmsg = '';
    if (@missingfile) {$errmsg .= "<p>missing:<ul><li>" . join ("</li><li>", @missingfile) . "</li></ul></p>"}
    if (@extrafile)   {$errmsg .= "<p>extra:<ul><li>"   . join ("</li><li>", @extrafile) . "</li></ul></p>"}

    &PrintMessage("Your submission has missing and/or extra file(s)." . $errmsg);
} # if
###

my $msg = '';

system ("chmod -R 777 $wdir");
system ("dos2unix $wdir/*.a2");

# check format of the files
$cmd = "$checker $wdir/*.a2 2>&1";
$errmsg = `$cmd`;
if ($errmsg) {
    system ("rm -r $wdir");
    $errmsg =~ s/$wdir\///g;
    &logging ($email, "format error detected.\n");
    &errlog  ($email, "format error detected:\n$errmsg\n");
    &PrintMessage("The following problem(s) were detected in your submission:<br/><pre>$errmsg</pre>");
} # if


## check last submission
my %last_sub = ();
open (SFILE, $timefile) or &PrintMessage ("cannot open time file.");
while (<SFILE>) {chomp; my ($user, $last) = split "\t"; $last_sub{$user} = $last}
close (SFILE);

my $now = time;
if ($last_sub{$email}) {
    my $r_seconds = ($access_limit * 3600) - ($now - $last_sub{$email});
    if ($r_seconds > 0) {
        system ("rm -r $wdir");
        &PrintMessage ("Your submission has passed format checking without problem.<br>However, the test set online evaluation is available only once per $access_limit hours for one team.<br/>It will next be available for you in " . (int ($r_seconds / 3600) + 1) . " hours.");
    } # if
} # if


## update the last submission log file
$last_sub{$email} = $now;
open (SFILE, ">", $timefile) or &PrintMessage ("cannot open $timefile for update.");
flock(LOGFILE, 2);
foreach (keys %last_sub) {print SFILE "$_\t$last_sub{$_}\n"}
flock(LOGFILE, 8);
close (SFILE);


# to decompose events (it is specific to the GE task)
$cmd = "$decomposer $wdir/*.a2 2>&1";
$errmsg = `$cmd`;
if ($errmsg) {
    system ("rm -r $wdir");
    $errmsg =~ s/$wdir\///g;
    &logging ($email, "logical error detected.\n");
    &errlog  ($email, "logical error detected:\n$errmsg\n");
    &PrintMessage("The following problem(s) were detected in your submission:<br/><pre>$errmsg</pre>");
} # if


# to collect the submissions
# if (!$msg) {
#     my ($sec, $min, $hour, $day, $mon) = (localtime)[0 .. 4]; $mon++;
#     my $ctime = "$mon-$day-$hour-$min-$sec";
#     $cmd = "cp $wdir/$sfile $cdir/$email-$ctime.tar.gz";
#     $errmsg = `$cmd`;
# } # if


## evaluation

# for task 1
my $result1     = `$evaluator  -t1     $wdir/*.a2`;
my $result1sp   = `$evaluator  -t1 -ps $wdir/*.a2`;
my $result1Sp   = `$evaluator  -t1 -pS $wdir/*.a2`;
my $result1spd  = `$devaluator -t1 -ps $wdir/*.a2d`;
my $result1Spd  = `$devaluator -t1 -pS $wdir/*.a2d`;

# for task 2
my $result2d    = `$devaluator -t2     $wdir/*.a2d`;
my $result2spd  = `$devaluator -t2 -ps $wdir/*.a2d`;
my $result2Spd  = `$devaluator -t2 -pS $wdir/*.a2d`;


# for task 3
my $result3    = `$evaluator -t3      $wdir/*.a2`;
my $result3sp  = `$evaluator -t3  -ps $wdir/*.a2`;
my $result3Sp  = `$evaluator -t3  -pS $wdir/*.a2`;


# clean-up the directory
system ("rm -r $wdir");

my $logmsg = "got evaluation results\n##### TASK 1\n[approx span/recursive]\n$result1sp\n##### TASK 2\n[approx span/recursive/decompose]\n$result2spd\n##### TASK 3\n[approx span/recursive]\n$result3sp\n\n";

my @logmsg = split /\n/, $logmsg;
$logmsg = join "\n", grep {!/^\[F[PN]]  /} @logmsg;


&logging ($email, $logmsg . "\n");
#&PrintMessage("evaluation done!");


&PrintResult($msg,
             $result1,  $result1sp,  $result1Sp, $result1spd, $result1Spd,
             $result2d, $result2spd, $result2Spd,
             $result3,  $result3sp,  $result3Sp);



sub logging {
    my ($email, $event) = @_;
    open (LOGFILE, ">> $logfile") ;
    flock(LOGFILE, 2);
    seek(LOGFILE, 0, 2);
    my $datetime = localtime;
    print LOGFILE "[$datetime / $email] $event\n" ;
    flock(LOGFILE, 8);
    close (LOGFILE);
} # logging


sub errlog {
    my ($email, $event) = @_;
    open (LOGFILE, ">> $errfile") ;
    flock(LOGFILE, 2);
    seek(LOGFILE, 0, 2);
    my $datetime = localtime;
    print LOGFILE "[$datetime / $email] $event\n" ;
    flock(LOGFILE, 8);
    close (LOGFILE);
} # errlog


sub PrintResult {
    my ($msg,
	$result1,  $result1sp,  $result1Sp, $result1spd, $result1Spd,
	$result2d, $result2spd, $result2Spd,
	$result3,  $result3sp,  $result3Sp) = @_;

    my $template = HTML::Template->new(filename => 'result.tmpl');

    $template->param(MESSAGE => $msg,
		     RESULT1  => $result1,  RESULT1SP   => $result1sp,  RESULT1ZP  => $result1Sp,  RESULT1SPD => $result1spd, RESULT1ZPD => $result1Spd,
		     RESULT2D => $result2d, RESULT2SPD  => $result2spd, RESULT2ZPD => $result2Spd,
		     RESULT3  => $result3,  RESULT3SP   => $result3sp,  RESULT3ZP  => $result3Sp);
    print "Content-Type: text/html\n\n", $template->output;
    exit;
} # PrintResult


sub PrintMessage {
    my ($msg) = shift;
    my $template = HTML::Template->new(filename => 'message.tmpl');

    $template->param(MSG => $msg);
    print "Content-Type: text/html\n\n", $template->output;
    exit;
} # PrintMessage
