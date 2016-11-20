#!/usr/bin/perl

######## WORK IN PROGRESS -- NOT FIT FOR USE -- WON'T WORK OR WILL BE USELESS ##########

use strict;
use warnings;
use Carp;
use List::Util qw(max reduce sum);

my $LOG_DIR = "/cygdrive/c/Users/$ENV{USER}/Documents/Paradox Interactive/Crusader Kings II/logs";
my $WIDTH = 120;

my $log_leaf = (@ARGV) ? shift @ARGV : 'error.log';
my $log_file = "$LOG_DIR/$log_leaf";
croak "file not found: $log_file" unless -e $log_file;

my @title_missing_loc;
my %title_missing_loc_ignore = ('---' => 1);
my @char_invalid_in_title_history;
my @char_bad_spouse;
my @char_bad_father;
my @char_bad_mother;
my @char_male_mom;
my @char_female_dad;
my @char_samesex_spouse;
my @title_unlanded_char;
my @prov_setup_bad_title;
my @prov_setup_bad_max_settlements;
my @title_holder_unborn;
my @title_redefined;
my @region_bad_elem;
my @region_mult_elem;
my @prov_bad_barony;

my @unrecognized_lines = (); # that weren't filtered due to being uninteresting

open(my $f, '<:crlf', $log_file) or croak "open: $!: $log_file";
my $n_line = 0;

while (<$f>) {
	++$n_line;
	next if /^\s*$/;
	next if /^\*+$/;
	next if /^\[internationalizedtext\.cpp:/;
	next if /Terrain for \d+ does not correspond to history.$/;
	next if /"Duchy defined in region not found. See log."$/;
	next if /"Region have multiple entries of the same province!"$/;

	if (/Missing localization for ([\w-]+)$/) {
		next if exists $title_missing_loc_ignore{$1};
		push @title_missing_loc, [$1,];
	}
	elsif (m|Invalid character (\d+) in history/titles/([\w-]+)\.txt$|) {
		push @char_invalid_in_title_history, [$1, $2];
	}
	elsif (/Tried to marry wife that does not exist. ID:(\d+) tried to marry ID: (\d+)$/) {
		push @char_bad_spouse, [$1, $2];
	}
	elsif (/Bad Father for character: (.+?) \((\d+)\)$/) {
		push @char_bad_father, [$2];
	}
	elsif (/Bad Mother for character: (.+?) \((\d+)\)$/) {
		push @char_bad_mother, [$2];
	}
	elsif (/Character ID:(\d+) has a female father!$/) {
		push @char_female_dad, [$1];
	}
	elsif (/Character ID:(\d+) has a male mother!$/) {
		push @char_male_mom, [$1];
	}
	elsif (/Same sex marriage. ID:(\d+) is married to ID: (\d+)$/) {
		push @char_samesex_spouse, [$1, $2];
	}
	elsif (/Character ID:(\d+) holds title '([\w-]+)', but no baronies!$/) {
		push @title_unlanded_char, [$2, $1];
	}
	elsif (/Barony '([\w-]+)' in the wrong province: (.+)$/) {
		push @prov_bad_barony, [$2, $1];
	}
	elsif (m|Error in common/province_setup/([\w \.+-]*?): Title for (\d+) does not correspond to history.$|) {
		push @prov_setup_bad_title, [$2, $1];
	}
	elsif (m|Error in common/province_setup/([\w \.+-]*?): Max settlements for (\d+) does not correspond to history.$|) {
		push @prov_setup_bad_max_settlements, [$2, $1];
	}
	elsif (m{Bad capital title '([\w-]+)' in province (\d+)$}) {
		# uh, placeholder until I know what that means
		push @unrecognized_lines, $_;
	}
	elsif (m{(?:duchy|county|province) '?([\w\-]+)'? defined in region '([\w\-]+)' not found$}i) {
		push @region_bad_elem, [$2, $1];
	}
	elsif (m{Region '([\w\-]+)' have multiple entries for the (?:duchy|county|province) '([\w\-]+)'$}i) {
		push @region_mult_elem, [$1, $2];
	}
	elsif (/Unborn title holder$/) {
		my $line = get_line($f);
		$line =~ m|^\tTitle: ([\w-]+)\(|;
		my $title = $1;
		$line = get_line($f);
		$line =~ m|^\tDate: ([\d\.]+)$|;
		my $date = $1;
		$line = get_line($f);
		$line =~ m|^\tCharacter ID: (\d+), Birth date: ([\d\.]+)$|;
		my ($char, $birthdate) = ($1, $2);
		push @title_holder_unborn, [$title, $char, $date, $birthdate];
	}
	elsif (/Title Already Exists!$/) {
		my $line = get_line($f);
		$line =~ m|^\tTitle: ([\w-]+)$|;
		my $title = $1;
		$line = get_line($f);
		$line =~ m|^\tLocation: common/landed_titles/([\w \.+-]*?)\((\d+)\)$|;
		push @title_redefined, [$title, $1, $2];
	}
	else {
		push @unrecognized_lines, $_;
	}
}

$f->close;

my $old_fh = select STDERR;
print @unrecognized_lines;
select $old_fh;

sub markup_province {
	($_[0] =~ /^\d+$/) ? "province_id[$_[0]]" : $_[0];
}

sub aligned_date {
	my ($y, $m, $d) = split(/\./, $_[0]);
	sprintf("%4s.%2s.%2s", $y, $m, $d);
}

print_data_table(
	title => "titles missing localisation",
	data => \@title_missing_loc,
	suppress_header => 1,
	cols => [
		{
			title => "Title",
			left_align => 1,
		},
	],
);
print_data_table(
	title => "invalid spouse for character",
	data => \@char_bad_spouse,
	numeric_sort => 1,
	cols => [
		{
			title => "Character ID",
		},
		{
			title => "Spouse ID",
			left_align => 1,
		},
	]
);
print_data_table(
	title => "character has same-sex marriage",
	data => \@char_samesex_spouse,
	numeric_sort => 1,
	cols => [
		{
			title => "Character ID",
		},
		{
			title => "Spouse ID",
			left_align => 1,
		},
	]
);
print_data_table(
	title => "invalid father for character",
	data => \@char_bad_father,
	numeric_sort => 1,
	suppress_header => 1,
	cols => [
		{
			title => "Character ID",
			left_align => 1,
		},
	],
);
print_data_table(
	title => "invalid mother for character",
	data => \@char_bad_mother,
	numeric_sort => 1,
	suppress_header => 1,
	cols => [
		{
			title => "Character ID",
			left_align => 1,
		},
	],
);
print_data_table(
	title => "character has female father",
	data => \@char_female_dad,
	numeric_sort => 1,
	suppress_header => 1,
	cols => [
		{
			title => "Character ID",
			left_align => 1,
		},
	],
);
print_data_table(
	title => "character has male mother",
	data => \@char_male_mom,
	numeric_sort => 1,
	suppress_header => 1,
	cols => [
		{
			title => "Character ID",
			left_align => 1,
		},
	],
);
print_data_table(
	title => "province has out-of-place barony",
	data => \@prov_bad_barony,
	numeric_sort => 1,
	cols => [
		{
			title => "Province ID",
		},
		{
			title => "Barony Title",
			left_align => 1,
		},
	]
);
print_data_table(
	title => "province setup: incorrect title",
	data => \@prov_setup_bad_title,
	numeric_sort => 1,
	cols => [
		{
			title => "Province ID",
			left_align => 1,
		},
	],
);
print_data_table(
	title => "province setup: incorrect max_settlements",
	data => \@prov_setup_bad_max_settlements,
	numeric_sort => 1,
	cols => [
		{
			title => "Province ID",
			left_align => 1,
		},
	],
);
print_data_table(
	title => "landed title held by character with no demesne",
	data => \@title_unlanded_char,
	cols => [
		{
			title => "Title",
		},
		{
			title => "Character ID",
			left_align => 1,
		},
	],
);
print_data_table(
	title => "invalid character in title history",
	data => \@char_invalid_in_title_history,
	numeric_sort => 1,
	cols => [
		{
			title => "Character ID",
		},
		{
			title => "Title",
			left_align => 1,
		},
	]
);
print_data_table(
	title => "title holder not yet born",
	data => \@title_holder_unborn,
	cols => [
		{
			title => "Title",
		},
		{
			title => "Character ID",
			left_align => 1,
		},
		{
			title => "Date Held",
			left_align => 1,
			observer => \&aligned_date,
		},
		{
			title => "Date Born",
			left_align => 1,
			observer => \&aligned_date,
		},
	]
);
print_data_table(
	title => "title redefinitions",
	data => \@title_redefined,
	cols => [
		{
			title => "Title",
		},
		{
			title => "Filename",
		},
		{
			title => "Line",
			left_align => 1,
		},
	]
);
print_data_table(
	title => "regions with undefined titles",
	data => \@region_bad_elem,
	cols => [
		{
			title => "Region",
		},
		{
			title => "Title",
			left_align => 1,
		},
	]
);
print_data_table(
	title => "regions with repeated elements",
	data => \@region_mult_elem,
	cols => [
		{
			title => "Region",
		},
		{
			title => "Element",
			left_align => 1,
			observer => \&markup_province,
		},
	]
);

exit 0;

########

sub maxlen(@) { length reduce { length($a) > length($b) ? $a : $b } @_ }

sub print_data_table {
	my %tbl = @_;
	return unless @{ $tbl{data} };

	my @cols = @{ $tbl{cols} };
	map { $_->{maxlen} = length $_->{title} } @cols;
	map { $_->{pad} = 0 } @cols;

	for my $row (@{ $tbl{data} }) {
		for my $i (0..$#cols) {
			my $c = $cols[$i];
			$row->[$i] = (defined $c->{observer}) ? &{$c->{observer}}( $row->[$i] ) : $row->[$i];
			$c->{maxlen} = max $c->{maxlen}, length $row->[$i];
		}
	}

	my $caption = " \U$tbl{title} ";
	my $caption_len = length $caption;
	my $data_width = -1 + sum map { $_->{maxlen} + 2 + 1 } @cols;

	if ($caption_len > $data_width) {
		my $caption_excess = $caption_len - $data_width;
		my $caption_excess_per_col = int($caption_excess / scalar @cols);
		my $caption_excess_remainder = $caption_excess % scalar @cols;

		for my $c (@cols) {
			$c->{pad} += $caption_excess_per_col;

			if ($caption_excess_remainder > 0) {
				--$caption_excess_remainder;
				++$c->{pad};
			}
		}

		$data_width = $caption_len;
	}

	my $caption_pad = $data_width - $caption_len;
	my $caption_pad_left = $caption_pad / 2;
	my $caption_pad_right = $caption_pad_left + $caption_pad % 2;

	print "\n/", '-' x $data_width, "\\\n";
	print "|", ' ' x $caption_pad_left, $caption, ' ' x $caption_pad_right, "|\n";

	my $sep_line = reduce { "$a".('-' x ($b->{maxlen} + $b->{pad} + 2)).'+' } '+', @cols;

	my $hdr_line = '|';

	for my $c (@cols) {
		my $pt = " \u$c->{title} ";
		my $align_char = '';
		$align_char = '-' if defined $c->{left_align};
		$hdr_line .= sprintf("%$align_char*s|", $c->{maxlen} + $c->{pad} + 2, $pt);
	}

	print "$sep_line\n";

	unless (exists $tbl{suppress_header} && $tbl{suppress_header}) {
		print "$hdr_line\n";
		print "$sep_line\n";
	}

	my $row_fmt = '|';

	for my $c (@cols) {
		my $align = $c->{maxlen} + $c->{pad};
		$align = '-'.$align if defined $c->{left_align};
		$row_fmt .= ' %'.$align.'s |';
	}

	$row_fmt .= "\n";

	my @rows = (exists $tbl{numeric_sort} && $tbl{numeric_sort})
		? sort { 0+$a->[0] <=> 0+$b->[0] } @{ $tbl{data} }
		: sort { $a->[0] cmp $b->[0] } @{ $tbl{data} };

	for my $row (@rows) {
		no warnings;
		printf($row_fmt, @$row);
	}

	print "\\", '-' x $data_width, "/\n";
}


sub get_line {
	my $fh = shift;
	defined(my $line = <$fh>) or croak "unexpected EOF or I/O error on input line $n_line: $!";
	++$n_line;
	return $line;
}
